# routers/brain.py
import json
import base64
import asyncio
import traceback
import websockets
import os
from datetime import datetime
from fastapi import WebSocket
from dotenv import load_dotenv
from services.agent_logic import process_agent_text_response, handle_user_slot_query

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
    context_str = f"\n\nCONTEXT: Today is {current_time}.\n\nCLINIC DATA:\n{clinic_data}"
    agent_config["agent"]["think"]["prompt"] += context_str
    log("Config loaded. Time and clinic data injected.")
    return agent_config


async def process_audio_stream(websocket: WebSocket) -> None:
    log("=" * 60)
    log("NEW CALL SESSION STARTED")
    log(f"websockets version: {websockets.__version__}")

    # --- API Key Check ---
    if not DEEPGRAM_API_KEY:
        log("FATAL: DEEPGRAM_API_KEY is not set in environment!")
        return
    log(f"DEEPGRAM_API_KEY loaded. Length={len(DEEPGRAM_API_KEY)}, Starts with: {DEEPGRAM_API_KEY[:8]}...")

    start_time: datetime = datetime.utcnow()
    conversation_state: dict = {
        "first_name": None,
        "last_name": None,
        "appointment_date": None,
        "appointment_time": None,
        "reason": None
    }

    # --- Load Config ---
    try:
        agent_config: dict = load_agent_config()
        log(f"Config keys: {list(agent_config.keys())}")
    except Exception as e:
        log(f"FATAL: Config load failed: {e}")
        log(traceback.format_exc())
        return

    # --- Connect to Deepgram ---
    log(f"Connecting to: {AGENT_URL}")
    log(f"Using extra_headers auth (websockets {websockets.__version__})")

    try:
        async with websockets.connect(
            AGENT_URL,
            extra_headers={"Authorization": f"Token {DEEPGRAM_API_KEY}"},
            ping_interval=30,
            ping_timeout=60,
        ) as dg_agent:
            log("SUCCESS: Connected to Deepgram Agent API!")

            # --- Send config ---
            try:
                config_str = json.dumps(agent_config)
                await dg_agent.send(config_str)
                log(f"Config sent to Deepgram ({len(config_str)} bytes)")
            except Exception as e:
                log(f"ERROR sending config: {e}")
                log(traceback.format_exc())
                return

            stream_sid: str = None
            twilio_msg_count: int = 0
            dg_msg_count: int = 0

            # --- SENDER: Twilio → Deepgram ---
            async def send_mic_audio() -> None:
                nonlocal stream_sid, twilio_msg_count
                log("SENDER task started (Twilio → Deepgram)")
                try:
                    while True:
                        raw = await websocket.receive_text()
                        data: dict = json.loads(raw)
                        event = data.get("event", "unknown")

                        if event == "start":
                            stream_sid = data["start"]["streamSid"]
                            log(f"Twilio stream STARTED. streamSid={stream_sid}")

                        elif event == "media":
                            twilio_msg_count += 1
                            if twilio_msg_count == 1:
                                log("First audio frame received from Twilio — forwarding to Deepgram")
                            audio_bytes: bytes = base64.b64decode(data["media"]["payload"])
                            try:
                                await dg_agent.send(audio_bytes)
                            except websockets.exceptions.ConnectionClosedOK:
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
                                    }
                                }
                                await websocket.send_text(json.dumps(media_message))
                            else:
                                log("WARNING: Got audio from Deepgram but stream_sid is not set yet!")
                        else:
                            try:
                                msg: dict = json.loads(response)
                                msg_type = msg.get("type", "unknown")
                                log(f"Deepgram message #{dg_msg_count}: type={msg_type}")

                                if msg_type == "ConversationText":
                                    content: str = msg.get("content", "")
                                    role: str = msg.get("role", "unknown")
                                    log(f"  [{role}]: {content[:120]}")
                                    conversation_state = await process_agent_text_response(
                                        content, conversation_state, dg_agent
                                    )
                                    # Wait for AgentAudioDone before closing
                                    if conversation_state.get("session_should_end") and role == "assistant":
                                        log("Farewell detected — waiting for AgentAudioDone to close.")
                                        farewell_pending = True

                                elif msg_type == "FunctionCallRequest":
                                    fn_name  = msg.get("function_name", "")
                                    fn_id    = msg.get("function_call_id", "")
                                    fn_input = msg.get("input", {})
                                    log(f"FUNCTION CALL: {fn_name} | args={fn_input}")

                                    if fn_name == "book_appointment":
                                        from services.database import book_appointment as db_book_appt
                                        from services.tools import parse_date, check_availability, get_available_slots_tool

                                        first_name = fn_input.get("first_name", "")
                                        last_name  = fn_input.get("last_name", "")
                                        date_str   = fn_input.get("date", "")
                                        time_str   = fn_input.get("time", "")
                                        reason     = fn_input.get("reason", "")

                                        conversation_state.update({
                                            "first_name": first_name,
                                            "last_name": last_name,
                                            "appointment_date": date_str,
                                            "appointment_time": time_str,
                                            "reason": reason,
                                        })

                                        real_date = parse_date(date_str)
                                        if check_availability(real_date, time_str):
                                            success = db_book_appt(first_name, last_name, real_date, time_str, reason)
                                            if success:
                                                conversation_state["booking_confirmed"] = True
                                                result = (
                                                    f"Appointment confirmed. Booked for {first_name} {last_name} "
                                                    f"on {real_date} at {time_str} for {reason}. "
                                                    f"Now say a warm goodbye to the patient."
                                                )
                                                log(f"Booking confirmed: {first_name} {last_name} {real_date} {time_str}")
                                            else:
                                                result = "Booking failed due to a system error. Let the patient know and apologise."
                                        else:
                                            free_slots = get_available_slots_tool(real_date)
                                            slots_str  = ", ".join(free_slots) if free_slots else "no available slots"
                                            result = (
                                                f"That slot is unavailable. Available times on {real_date}: {slots_str}. "
                                                f"Ask the patient to choose another time."
                                            )
                                            log(f"Slot unavailable: {real_date} {time_str}. Free: {slots_str}")

                                        await dg_agent.send(json.dumps({
                                            "type": "FunctionCallResponse",
                                            "function_call_id": fn_id,
                                            "output": result,
                                        }))
                                        log(f"FunctionCallResponse sent: {result}")

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
                                log(f"Failed to parse Deepgram text response: {e} | raw={response[:200]}")

                except Exception as e:
                    log(f"ERROR in receive_agent_audio: {e}")
                    log(traceback.format_exc())

            # --- Run both tasks ---
            log("Starting sender and receiver tasks...")
            tasks = [
                asyncio.create_task(send_mic_audio()),
                asyncio.create_task(receive_agent_audio())
            ]

            done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)

            for task in done:
                if task.exception():
                    log(f"Task failed with exception: {task.exception()}")

            for task in pending:
                task.cancel()

            log(f"Call session ended. Twilio frames={twilio_msg_count}, Deepgram msgs={dg_msg_count}")

            # --- Log call to CSV ---
            try:
                from services.call_logger import append_call_log
                end_time: datetime = datetime.utcnow()
                call_duration: float = (end_time - start_time).total_seconds()
                patient_name: str = ""
                if conversation_state.get("first_name") and conversation_state.get("last_name"):
                    patient_name = f"{conversation_state['first_name']} {conversation_state['last_name']}"
                intent: str = "Booking" if conversation_state.get("booking_confirmed") else "FAQ"
                status: str = "Confirmed" if conversation_state.get("booking_confirmed") else "Follow-up Needed"
                append_call_log(
                    timestamp=end_time.isoformat(),
                    caller_id="unknown",
                    patient_name=patient_name,
                    call_duration=call_duration,
                    intent=intent,
                    summary=conversation_state.get("last_summary", ""),
                    status=status,
                    estimated_value=100.0 if conversation_state.get("booking_confirmed") else 0.0,
                    recording_url="",
                )
                log(f"Call logged. Duration={call_duration:.1f}s, Patient={patient_name or 'unknown'}")
            except Exception as e:
                log(f"ERROR logging call: {e}")
                log(traceback.format_exc())

    except websockets.exceptions.InvalidStatusCode as e:
        log(f"FATAL: Deepgram rejected connection. HTTP {e.status_code}")
        log(f"  Reason: Check Deepgram account credits and Voice Agent API access.")
        log(traceback.format_exc())
    except Exception as e:
        log(f"FATAL: Deepgram connection error: {type(e).__name__}: {e}")
        log(traceback.format_exc())

    log("=" * 60)
