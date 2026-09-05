import json
import asyncio
import websockets
import os
from datetime import datetime
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from dotenv import load_dotenv
from services.agent_logic import process_agent_text_response, handle_booking_function_call
from services.webhook_dispatcher import dispatch_call_completed

load_dotenv()

router = APIRouter()

DEEPGRAM_API_KEY = os.getenv("DEEPGRAM_API_KEY", "")
AGENT_URL = "wss://agent.deepgram.com/v1/agent/converse"


def load_voice_config() -> dict:
    with open("data/config.json", "r") as f:
        config = json.load(f)
    with open("data/data.json", "r") as f:
        clinic_data = f.read()

    config["audio"] = {
        "input":  {"encoding": "linear16", "sample_rate": 16000},
        "output": {"encoding": "linear16", "sample_rate": 24000, "container": "none"}
    }

    # 1200ms endpointing — gives user enough time to finish their sentence
    config["agent"]["listen"]["provider"]["endpointing"] = 1200

    current_time = datetime.now().strftime("%A, %d %B %Y, %I:%M %p")
    config["agent"]["think"]["prompt"] += f"\n\nCONTEXT: Today is {current_time}.\n\nHOTEL DATA:\n{clinic_data}"
    return config


@router.websocket("/voice-chat")
async def voice_chat(websocket: WebSocket):
    await websocket.accept()

    if not DEEPGRAM_API_KEY:
        await websocket.send_json({"type": "error", "content": "Missing API key"})
        await websocket.close()
        return

    headers = {"Authorization": f"Token {DEEPGRAM_API_KEY}"}

    try:
        config = load_voice_config()
    except Exception as e:
        print(f"[VOICE] Config error: {e}")
        await websocket.send_json({"type": "error", "content": str(e)})
        await websocket.close()
        return

    conversation_state = {
        "first_name": None, "last_name": None, "phone_number": None,
        "room_type": None, "check_in_date": None, "check_out_date": None,
        "number_of_guests": None, "special_requests": None,
        "booking_confirmed": False, "booking_id": None,
        "session_should_end": False,
        "last_message_is_payload": False,
    }

    session_active = True
    session_start = datetime.utcnow()

    try:
        async with websockets.connect(
            AGENT_URL,
            extra_headers={"Authorization": f"Token {DEEPGRAM_API_KEY}"},
        ) as dg_agent:
            await dg_agent.send(json.dumps(config))
            await websocket.send_json({"type": "connected"})
            print("[VOICE] Connected to Deepgram. Sarah is ready.")

            # ── Browser → Deepgram ──────────────────────────────────
            async def receive_from_browser():
                nonlocal session_active
                try:
                    while session_active:
                        try:
                            msg = await websocket.receive()
                            if msg["type"] == "websocket.disconnect":
                                session_active = False
                                return
                            raw = msg.get("bytes") or b""
                            if raw:
                                try:
                                    await dg_agent.send(raw)
                                except Exception:
                                    session_active = False
                                    return
                        except WebSocketDisconnect:
                            session_active = False
                            return
                        except Exception as e:
                            print(f"[VOICE] Browser recv error: {e}")
                            session_active = False
                            return
                except asyncio.CancelledError:
                    pass

            # ── Deepgram → Browser ──────────────────────────────────
            async def receive_from_deepgram():
                nonlocal conversation_state, session_active
                try:
                    while session_active:
                        try:
                            response = await dg_agent.recv()
                        except Exception as e:
                            print(f"[VOICE] Deepgram recv error: {e}")
                            session_active = False
                            return

                        if isinstance(response, bytes):
                            try:
                                await websocket.send_bytes(response)
                            except Exception:
                                session_active = False
                                return
                        else:
                            try:
                                msg = json.loads(response)
                            except Exception:
                                continue

                            msg_type = msg.get("type", "")

                            if msg_type == "ConversationText":
                                content = msg.get("content", "")
                                role    = msg.get("role", "assistant")

                                if role == "assistant":
                                    # Only run agent logic on assistant messages to avoid
                                    # farewell detection or JSON parsing firing on user speech.
                                    conversation_state = await process_agent_text_response(
                                        content, conversation_state, dg_agent
                                    )

                                # User speech is never a payload — use stale flag only for assistant.
                                is_payload = (role == "assistant") and conversation_state.get("last_message_is_payload", False)
                                is_system = content.strip().startswith("[SYSTEM]")
                                if not is_payload and not is_system:
                                    try:
                                        await websocket.send_json({
                                            "type": "transcript",
                                            "role": role,
                                            "content": content
                                        })
                                    except Exception:
                                        session_active = False
                                        return
                                # Don't close here — wait for AgentAudioDone so
                                # Sarah finishes speaking before the session ends.

                            elif msg_type == "FunctionCallRequest":
                                functions_list = msg.get("functions", [])
                                if not functions_list:
                                    print("[VOICE] FunctionCallRequest has empty functions array — skipping.")
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
                                print(f"[VOICE] FUNCTION CALL: {fn_name} | id={fn_id} | args={fn_input}")

                                result = f"Function '{fn_name}' is not available."

                                if fn_name == "book_room":
                                    result = await handle_booking_function_call(
                                        fn_input, conversation_state, dg_agent, None
                                    )

                                try:
                                    await dg_agent.send(json.dumps({
                                        "type": "FunctionCallResponse",
                                        "id": fn_id,
                                        "output": result,
                                    }))
                                except Exception as e:
                                    print(f"[VOICE] FunctionCallResponse send error: {e}")

                            elif msg_type == "AgentAudioDone":
                                if conversation_state.get("session_should_end"):
                                    # Audio fully delivered — give browser 1 s to finish playback
                                    await asyncio.sleep(1)
                                    try:
                                        await websocket.send_json({"type": "session_ended"})
                                    except Exception:
                                        pass
                                    session_active = False
                                    return

                            elif msg_type == "UserStartedSpeaking":
                                try: await websocket.send_json({"type": "user_speaking"})
                                except Exception: pass

                            elif msg_type == "AgentThinking":
                                try: await websocket.send_json({"type": "agent_thinking"})
                                except Exception: pass

                            elif msg_type == "AgentStartedSpeaking":
                                try: await websocket.send_json({"type": "agent_speaking"})
                                except Exception: pass

                except asyncio.CancelledError:
                    pass

            async def send_keepalive():
                try:
                    while session_active:
                        await asyncio.sleep(10)
                        if not session_active:
                            break
                        try:
                            await dg_agent.send(json.dumps({"type": "KeepAlive"}))
                        except Exception:
                            break
                except asyncio.CancelledError:
                    pass

            tasks = [
                asyncio.create_task(receive_from_browser()),
                asyncio.create_task(receive_from_deepgram()),
                asyncio.create_task(send_keepalive()),
            ]
            done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            session_active = False
            for task in pending:
                task.cancel()
                try:
                    await asyncio.wait_for(task, timeout=2.0)
                except (asyncio.CancelledError, asyncio.TimeoutError):
                    pass

            try:
                dispatch_call_completed({
                    "caller_id": "voice-browser",
                    "to_number": "voice-browser",
                    "duration_seconds": int((datetime.utcnow() - session_start).total_seconds()),
                    "booking_confirmed": bool(conversation_state.get("booking_confirmed")),
                    "booking_id": conversation_state.get("booking_id"),
                }, None)
            except Exception as e:
                print(f"[VOICE] call.completed dispatch error: {e}")

    except Exception as e:
        print(f"[VOICE] Connection error: {e}")
        try:
            await websocket.send_json({"type": "error", "content": str(e)})
        except Exception:
            pass
