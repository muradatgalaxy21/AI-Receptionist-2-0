# routers/brain.py
import json
import base64
import asyncio
import traceback
import websockets
import os
from datetime import datetime
from fastapi import WebSocket
from starlette.websockets import WebSocketDisconnect
from dotenv import load_dotenv
from services.agent_logic import (
    process_agent_text_response,
    handle_booking_function_call,
)
from services.webhook_dispatcher import dispatch_call_completed

load_dotenv()

DEEPGRAM_API_KEY: str = os.getenv("DEEPGRAM_API_KEY", "")
AGENT_URL: str = "wss://agent.deepgram.com/v1/agent/converse"


def log(msg: str):
    print(f"[BRAIN] {msg}", flush=True)


def load_agent_config() -> dict:
    with open("data/config.json", "r") as f:
        agent_config: dict = json.load(f)

    with open("data/data.json", "r") as f:
        clinic_data: str = f.read()

    current_time: str = datetime.now().strftime("%A, %d %B %Y, %I:%M %p")
    context_str = f"\n\nCONTEXT: Today is {current_time}.\n\nHOTEL DATA:\n{clinic_data}"
    agent_config["agent"]["think"]["prompt"] += context_str
    log("Config loaded. Time and clinic data injected.")
    return agent_config


async def process_audio_stream(websocket: WebSocket, caller_id: str = "unknown", to_number: str = "unknown") -> None:
    log("=" * 60)
    log("NEW CALL SESSION STARTED")
    log(f"websockets version: {websockets.__version__}")

    if not DEEPGRAM_API_KEY:
        log("FATAL: DEEPGRAM_API_KEY is not set in environment!")
        return
    log(f"DEEPGRAM_API_KEY loaded. Length={len(DEEPGRAM_API_KEY)}, Starts with: {DEEPGRAM_API_KEY[:8]}...")

    start_time: datetime = datetime.utcnow()
    transcript_lines: list = []
    conversation_state: dict = {
        "first_name": None,
        "last_name": None,
        "phone_number": None,
        "room_type": None,
        "check_in_date": None,
        "check_out_date": None,
        "number_of_guests": None,
        "special_requests": None,
        "booking_confirmed": False,
        "booking_id": None,
        "session_should_end": False,
        "last_message_is_payload": False,
    }

    try:
        agent_config: dict = load_agent_config()
        log(f"Config keys: {list(agent_config.keys())}")
    except Exception as e:
        log(f"FATAL: Config load failed: {e}")
        log(traceback.format_exc())
        return

    log(f"Connecting to: {AGENT_URL}")

    try:
        async with websockets.connect(
            AGENT_URL,
            extra_headers={"Authorization": f"Token {DEEPGRAM_API_KEY}"},
            ping_interval=30,
            ping_timeout=60,
        ) as dg_agent:
            log("SUCCESS: Connected to Deepgram Agent API!")

            try:
                config_str = json.dumps(agent_config)
                await dg_agent.send(config_str)
                log(f"Config sent to Deepgram ({len(config_str)} bytes)")
            except Exception as e:
                log(f"ERROR sending config: {e}")
                log(traceback.format_exc())
                return

            stream_sid: str = None
            call_sid: str = None
            twilio_msg_count: int = 0
            dg_msg_count: int = 0

            # --- SENDER: Twilio → Deepgram ---
            async def send_mic_audio() -> None:
                nonlocal stream_sid, call_sid, twilio_msg_count, caller_id, to_number
                log("SENDER task started (Twilio → Deepgram)")
                try:
                    while True:
                        raw = await websocket.receive_text()
                        try:
                            data: dict = json.loads(raw)
                        except json.JSONDecodeError as e:
                            log(f"Invalid JSON from Twilio: {e}")
                            continue
                        event = data.get("event", "unknown")

                        if event == "start":
                            start_data = data.get("start", {})
                            stream_sid = start_data.get("streamSid")
                            call_sid = start_data.get("callSid")
                            # Twilio sends query params as customParameters inside the start event
                            custom = start_data.get("customParameters", {})
                            if custom.get("caller_id"):
                                caller_id = custom["caller_id"]
                            if custom.get("to_number"):
                                to_number = custom["to_number"]
                            log(f"Twilio stream STARTED. streamSid={stream_sid}, caller={caller_id}, to={to_number}")

                        elif event == "media":
                            twilio_msg_count += 1
                            if twilio_msg_count == 1:
                                log("First audio frame received from Twilio — forwarding to Deepgram")
                            payload_b64 = data.get("media", {}).get("payload")
                            if not payload_b64:
                                continue
                            audio_bytes: bytes = base64.b64decode(payload_b64)
                            try:
                                await dg_agent.send(audio_bytes)
                            except (websockets.exceptions.ConnectionClosedOK,
                                    websockets.exceptions.ConnectionClosedError):
                                # Deepgram session ended cleanly — stop forwarding
                                break
                            except Exception as e:
                                log(f"ERROR forwarding audio to Deepgram: {e}")
                                log(traceback.format_exc())
                                break

                        elif event == "stop":
                            log(f"Twilio stream STOPPED. Total audio frames sent: {twilio_msg_count}")
                            break

                        else:
                            log(f"Unknown Twilio event: {event}")

                except WebSocketDisconnect:
                    log("Twilio WebSocket disconnected — caller hung up.")
                except Exception as e:
                    log(f"ERROR in send_mic_audio: {e}")
                    log(traceback.format_exc())

            # --- RECEIVER: Deepgram → Twilio ---
            async def receive_agent_audio() -> None:
                nonlocal conversation_state, dg_msg_count
                farewell_pending: bool = False
                log("RECEIVER task started (Deepgram → Twilio)")
                try:
                    while True:
                        response = await dg_agent.recv()
                        dg_msg_count += 1

                        if isinstance(response, bytes):
                            if dg_msg_count <= 3:
                                log(f"Audio bytes received from Deepgram ({len(response)} bytes) — forwarding to Twilio")
                            if stream_sid:
                                media_message: dict = {
                                    "event": "media",
                                    "streamSid": stream_sid,
                                    "media": {
                                        "payload": base64.b64encode(response).decode("utf-8")
                                    },
                                }
                                try:
                                    await websocket.send_text(json.dumps(media_message))
                                except (WebSocketDisconnect, Exception):
                                    log("Twilio WebSocket closed while sending audio — caller hung up.")
                                    return
                            else:
                                log("WARNING: Got audio from Deepgram but stream_sid not set yet!")

                        else:
                            try:
                                msg: dict = json.loads(response)
                                msg_type = msg.get("type", "unknown")
                                log(f"Deepgram message #{dg_msg_count}: type={msg_type}")

                                if msg_type == "ConversationText":
                                    content: str = msg.get("content", "")
                                    role: str = msg.get("role", "unknown")
                                    log(f"  [{role}]: {content[:120]}")
                                    
                                    # Save to dynamic conversation transcript
                                    speaker = "Guest" if role == "user" else "Sarah"
                                    transcript_lines.append(f"{speaker}: {content}")

                                    if role == "assistant":
                                        conversation_state = await process_agent_text_response(
                                            content, conversation_state, dg_agent, call_sid
                                        )
                                        if conversation_state.get("session_should_end"):
                                            log("Farewell detected — waiting for AgentAudioDone to close.")
                                            farewell_pending = True

                                elif msg_type == "FunctionCallRequest":
                                    # Deepgram sends FunctionCallRequest as a "functions" array.
                                    # Each element has: id (str), name (str), arguments (JSON string).
                                    log(f"FunctionCallRequest raw: {response[:400]}")
                                    functions_list = msg.get("functions", [])
                                    if not functions_list:
                                        log("WARNING: FunctionCallRequest has empty functions array — skipping.")
                                        continue
                                    fn_obj   = functions_list[0]
                                    fn_name  = fn_obj.get("name", "")
                                    fn_id    = fn_obj.get("id", "")
                                    fn_args_raw = fn_obj.get("arguments", "{}")
                                    try:
                                        fn_input = json.loads(fn_args_raw) if fn_args_raw else {}
                                    except (json.JSONDecodeError, ValueError):
                                        fn_input = {}
                                    if not isinstance(fn_input, dict):
                                        fn_input = {}
                                    log(f"FUNCTION CALL: {fn_name} | id={fn_id} | args={fn_input}")

                                    # Default result — handles any unexpected function name
                                    # so Deepgram never hangs waiting for a response.
                                    result = f"Function '{fn_name}' is not available."

                                    if fn_name == "book_room":
                                        result = await handle_booking_function_call(
                                            fn_input, conversation_state, dg_agent, call_sid
                                        )
                                        log(f"book_room -> {result[:120]}")

                                    await dg_agent.send(json.dumps({
                                        "type": "FunctionCallResponse",
                                        "id": fn_id,
                                        "name": fn_name,
                                        "content": result,
                                    }))
                                    log(f"FunctionCallResponse sent: {result[:100]}")

                                elif msg_type == "AgentAudioDone":
                                    if farewell_pending:
                                        log("AgentAudioDone after farewell — closing session.")
                                        await asyncio.sleep(0.5)
                                        await dg_agent.close()
                                        return

                                elif msg_type == "Error":
                                    log(f"ERROR from Deepgram: {response}")
                                elif msg_type == "Warning":
                                    log(f"WARNING from Deepgram: {response}")
                                else:
                                    log(f"  Full message: {response[:300]}")

                            except json.JSONDecodeError as e:
                                log(f"Failed to parse Deepgram message: {e} | raw={response[:200]}")

                except (websockets.exceptions.ConnectionClosedOK,
                        websockets.exceptions.ConnectionClosedError):
                    log("Deepgram connection closed.")
                except Exception as e:
                    log(f"ERROR in receive_agent_audio: {e}")
                    log(traceback.format_exc())

            # --- KEEPALIVE: prevents Deepgram from closing idle connections ---
            async def send_keepalive() -> None:
                try:
                    while True:
                        await asyncio.sleep(10)
                        try:
                            await dg_agent.send(json.dumps({"type": "KeepAlive"}))
                        except (websockets.exceptions.ConnectionClosedOK,
                                websockets.exceptions.ConnectionClosedError):
                            break
                        except Exception as e:
                            log(f"Keepalive error: {e}")
                            break
                except asyncio.CancelledError:
                    pass

            # --- Run all tasks concurrently ---
            log("Starting sender and receiver tasks...")
            tasks = [
                asyncio.create_task(send_mic_audio()),
                asyncio.create_task(receive_agent_audio()),
                asyncio.create_task(send_keepalive()),
            ]

            done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)

            for task in done:
                exc = task.exception() if not task.cancelled() else None
                if exc:
                    log(f"Task finished with exception: {exc}")

            for task in pending:
                task.cancel()

            # Await cancelled tasks so they clean up properly
            if pending:
                await asyncio.gather(*pending, return_exceptions=True)

            log(f"Call session ended. Twilio frames={twilio_msg_count}, Deepgram msgs={dg_msg_count}")

            end_time: datetime = datetime.utcnow()
            call_duration: float = (end_time - start_time).total_seconds()
            booking_confirmed: bool = bool(conversation_state.get("booking_confirmed"))
            guest_name: str = ""
            if conversation_state.get("first_name") and conversation_state.get("last_name"):
                guest_name = f"{conversation_state['first_name']} {conversation_state['last_name']}"

            # --- Fire call.completed webhook (fire-and-forget) ---
            try:
                dispatch_call_completed({
                    "caller_id": caller_id,
                    "to_number": to_number,
                    "duration_seconds": int(call_duration),
                    "booking_confirmed": booking_confirmed,
                    "booking_id": conversation_state.get("booking_id"),
                }, call_sid)
            except Exception as e:
                log(f"ERROR dispatching call.completed: {e}")

            # --- Log call to the database ---
            try:
                from services.call_logger import append_call_log
                intent: str = "Reservation" if booking_confirmed else "FAQ"
                status: str = "Confirmed" if booking_confirmed else "Completed"
                transcript_str = "\n".join(transcript_lines)
                append_call_log(
                    timestamp=end_time.isoformat(),
                    caller_id=caller_id,
                    to_number=to_number,
                    patient_name=guest_name,
                    call_duration=call_duration,
                    intent=intent,
                    summary=conversation_state.get("last_summary", ""),
                    transcript=transcript_str,
                    status=status,
                    estimated_value=float(conversation_state.get("total_cost") or 0.0),
                    recording_url="",
                )
                log(f"Call logged. Caller={caller_id}, Dialed={to_number}, Duration={call_duration:.1f}s, Guest={guest_name or 'unknown'}")
            except Exception as e:
                log(f"ERROR logging call: {e}")
                log(traceback.format_exc())

    except websockets.exceptions.InvalidStatusCode as e:
        log(f"FATAL: Deepgram rejected connection. HTTP {e.status_code}")
        log("Check Deepgram account credits and Voice Agent API access.")
        log(traceback.format_exc())
    except Exception as e:
        log(f"FATAL: Deepgram connection error: {type(e).__name__}: {e}")
        log(traceback.format_exc())

    log("=" * 60)
