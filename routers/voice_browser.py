import json
import asyncio
import websockets
import os
from datetime import datetime
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from dotenv import load_dotenv
from services.agent_logic import process_agent_text_response, handle_user_slot_query, handle_date_selection_in_booking

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
    config["agent"]["think"]["prompt"] += f"\n\nCONTEXT: Today is {current_time}.\n\nCLINIC DATA:\n{clinic_data}"
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
        "first_name": None, "last_name": None,
        "appointment_date": None, "appointment_time": None,
        "reason": None, "booking_confirmed": False,
        "session_should_end": False,
        "last_message_is_payload": False,
    }

    session_active = True

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

                                if role == "user":
                                    # Deepgram echoes InjectUserMessage back as role="user".
                                    # Check pending injection counter so we skip the echo —
                                    # don't show it in transcript and don't re-inject.
                                    pending_echoes = conversation_state.get("_pending_echoes", 0)
                                    if pending_echoes > 0:
                                        conversation_state["_pending_echoes"] = pending_echoes - 1
                                        continue

                                    # Real user speech — run slot/date injection
                                    handled = await handle_user_slot_query(content, conversation_state, dg_agent)
                                    if handled:
                                        conversation_state["_pending_echoes"] = conversation_state.get("_pending_echoes", 0) + 1
                                    else:
                                        injected = await handle_date_selection_in_booking(content, conversation_state, dg_agent)
                                        if injected:
                                            conversation_state["_pending_echoes"] = conversation_state.get("_pending_echoes", 0) + 1
                                else:
                                    # Only run agent logic processing on assistant messages to avoid
                                    # farewell detection or JSON parsing triggering on user speech.
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

                                if fn_name == "book_appointment":
                                    from services.database import book_appointment as db_book_appt
                                    from services.tools import parse_date, check_availability, get_available_slots_tool

                                    first_name = fn_input.get("first_name", "").strip()
                                    last_name  = fn_input.get("last_name", "").strip()
                                    date_str   = fn_input.get("date", "").strip()
                                    time_str   = fn_input.get("time", "").strip()
                                    reason     = fn_input.get("reason", "").strip()

                                    missing = [f for f, v in {
                                        "first_name": first_name, "last_name": last_name,
                                        "date": date_str, "time": time_str, "reason": reason,
                                    }.items() if not v]
                                    if missing:
                                        result = f"Missing fields: {', '.join(missing)}. Please ask the patient to provide them."
                                    else:
                                        real_date = parse_date(date_str)
                                        if not real_date:
                                            result = "Could not understand the date. Please ask the patient to repeat it clearly."
                                        elif check_availability(real_date, time_str):
                                            success = db_book_appt(first_name, last_name, real_date, time_str, reason)
                                            if success:
                                                conversation_state.update({
                                                    "first_name": first_name, "last_name": last_name,
                                                    "appointment_date": real_date, "appointment_time": time_str,
                                                    "reason": reason, "booking_confirmed": True,
                                                    "_booking_just_confirmed": True,
                                                })
                                                result = (
                                                    f"Appointment confirmed. Booked for {first_name} {last_name} "
                                                    f"on {real_date} at {time_str} for {reason}. "
                                                    f"Warmly tell the patient their appointment is booked, then ask: "
                                                    f"'Is there anything else I can help you with today?' "
                                                    f"Do NOT say goodbye or end the call — wait for the patient's response."
                                                )
                                            else:
                                                result = "Booking failed due to a system error. Please let the patient know and apologise."
                                        else:
                                            free_slots = get_available_slots_tool(real_date)
                                            slots_str = ", ".join(free_slots) if free_slots else "no available slots"
                                            result = (
                                                f"That slot is unavailable. Available times on {real_date}: {slots_str}. "
                                                f"Ask the patient to choose another time."
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

    except Exception as e:
        print(f"[VOICE] Connection error: {e}")
        try:
            await websocket.send_json({"type": "error", "content": str(e)})
        except Exception:
            pass
