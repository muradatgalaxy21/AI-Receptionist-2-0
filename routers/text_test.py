# routers/text_test.py
# WebSocket endpoint for text-based testing of the Deepgram agent.
# Allows a browser or API client to chat with Sarah via text instead of voice.
# Uses Deepgram's InjectUserMessage to feed text into the same agent pipeline.

import json
import asyncio
import websockets
import os
from typing import Optional
from datetime import datetime
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from dotenv import load_dotenv
from services.agent_logic import (
    process_agent_text_response,
    handle_booking_function_call,
)
from services.webhook_dispatcher import dispatch_call_completed
from services.conversation_logger import ConversationLogger

load_dotenv()

router = APIRouter()

DEEPGRAM_API_KEY: str = os.getenv("DEEPGRAM_API_KEY", "")
AGENT_URL: str = "wss://agent.deepgram.com/v1/agent/converse"

# Keepalive interval in seconds -- prevents Deepgram from closing idle connections
KEEPALIVE_INTERVAL_SECONDS: int = 5


def load_agent_config_for_text() -> dict:
    """
    Load and modify the agent config for text-only mode.
    """
    with open("data/config.json", "r") as f:
        agent_config: dict = json.load(f)

    with open("data/data.json", "r") as f:
        clinic_data: str = f.read()

    # Inject current date and time
    current_time: str = datetime.now().strftime("%A, %d %B %Y, %I:%M %p")
    
    context_str = f"\n\nCONTEXT: Today is {current_time}.\n\nHOTEL DATA:\n{clinic_data}"
    agent_config["agent"]["think"]["prompt"] += context_str
    print(f"[TEXT-TEST] Injecting time and clinic data into prompt.")

    return agent_config


@router.websocket("/test-chat")
async def text_chat(websocket: WebSocket) -> None:
    """
    WebSocket endpoint for text-based agent testing.
    Flow:
    1. Accept the browser/client WebSocket connection.
    2. Connect to Deepgram Agent API and send config.
    3. Run three concurrent tasks:
       - receive_from_agent: listens for Deepgram responses, sends text back to client
       - receive_from_client: listens for client text, injects it to Deepgram
       - send_keepalive: sends periodic KeepAlive messages to Deepgram
    4. Agent's audio output is discarded; only text responses are forwarded.
    5. Session stays alive until the browser client disconnects.
    """
    await websocket.accept()
    print("[TEXT-TEST] Client connected")

    logger: ConversationLogger = ConversationLogger(session_label="text_test")
    print(f"[TEXT-TEST] Logging to: {logger.file_path}")

    if not DEEPGRAM_API_KEY:
        await websocket.send_json({
            "role": "system",
            "content": "Error: DEEPGRAM_API_KEY is missing from .env file"
        })
        await websocket.close()
        return

    headers: dict = {"Authorization": f"Token {DEEPGRAM_API_KEY}"}

    try:
        agent_config: dict = load_agent_config_for_text()
    except Exception as e:
        await websocket.send_json({
            "role": "system",
            "content": f"Config Error: {e}"
        })
        await websocket.close()
        return

    # Track conversation state (same structure as the voice path)
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
    session_start: datetime = datetime.utcnow()

    # Shared flag so all tasks know when to stop
    session_active: bool = True

    try:
        async with websockets.connect(
            AGENT_URL,
            additional_headers=headers,
            # Enable built-in WebSocket ping/pong frames to detect dead connections
            ping_interval=20,
            ping_timeout=10,
        ) as dg_agent:
            # Send the agent configuration
            await dg_agent.send(json.dumps(agent_config))
            print("[TEXT-TEST] Connected to Deepgram Agent. Sarah is listening...")
            logger.log_event("Connected to Deepgram Agent")

            # Notify the client that the connection is ready
            await websocket.send_json({
                "role": "system",
                "content": "Connected to Sarah. You can start chatting."
            })

            # --- Task 1: Receive agent responses and forward to client ---
            async def receive_from_agent() -> None:
                """
                Continuously reads messages from the Deepgram agent WebSocket.
                1. Discards binary audio data (not needed in text mode).
                2. Forwards ConversationText messages to the browser client.
                3. Processes responses through shared agent logic for booking flow.
                4. Only exits when session_active is set to False.
                """
                nonlocal conversation_state, session_active
                try:
                    while session_active:
                        try:
                            response = await dg_agent.recv()
                        except websockets.exceptions.ConnectionClosed as e:
                            print(f"[TEXT-TEST] Deepgram connection closed: {e}")
                            # Notify client about the disconnection
                            if session_active:
                                try:
                                    await websocket.send_json({
                                        "role": "system",
                                        "content": "Deepgram agent connection closed. Please refresh."
                                    })
                                except Exception:
                                    pass
                            session_active = False
                            return

                        # Discard binary audio data in text mode
                        if isinstance(response, bytes):
                            continue

                        try:
                            msg: dict = json.loads(response)
                        except json.JSONDecodeError:
                            continue

                        msg_type: str = msg.get("type", "")

                        if msg_type == "ConversationText":
                            content: str = msg.get("content", "")
                            role: str = msg.get("role", "assistant")

                            if role == "assistant":
                                # Only process agent logic for assistant messages.
                                # Running it on user-role echoes could falsely trigger
                                # farewell detection if the user said 'goodbye' etc.
                                try:
                                    conversation_state = await process_agent_text_response(
                                        content, conversation_state, dg_agent
                                    )
                                except Exception as e:
                                    print(f"[TEXT-TEST] Agent logic error: {e}")

                                # Forward the agent's text response to the client.
                                # Skip if the message was a hidden JSON payload (e.g. ready_to_book).
                                is_payload: bool = conversation_state.get("last_message_is_payload", False)
                                if not is_payload:
                                    try:
                                        await websocket.send_json({
                                            "role": "assistant",
                                            "content": content
                                        })
                                        logger.log("SARAH", content)
                                    except Exception:
                                        session_active = False
                                        return

                                    if conversation_state.get("session_should_end"):
                                        print("[TEXT-TEST] Farewell detected. Closing session.")
                                        logger.log_event("Session ended by agent farewell")
                                        await asyncio.sleep(1.5)
                                        try:
                                            await websocket.send_json({"type": "session_ended"})
                                        except Exception:
                                            pass
                                        session_active = False
                                        return

                        elif msg_type == "UserStartedSpeaking":
                            # Text mode: this fires when InjectUserMessage is sent
                            pass

                        elif msg_type == "AgentThinking":
                            # Notify the client that the agent is thinking
                            try:
                                await websocket.send_json({
                                    "role": "system",
                                    "content": "Sarah is thinking..."
                                })
                            except Exception:
                                session_active = False
                                return

                        elif msg_type == "AgentAudioDone":
                            # Audio finished playing -- this is normal, NOT a disconnect signal
                            pass

                        elif msg_type == "InjectionRefused":
                            try:
                                await websocket.send_json({
                                    "role": "system",
                                    "content": "Message was not processed (agent was busy). Try again."
                                })
                            except Exception:
                                session_active = False
                                return

                        elif msg_type == "FunctionCallRequest":
                            functions_list = msg.get("functions", [])
                            if not functions_list:
                                print("[TEXT-TEST] FunctionCallRequest has empty functions array — skipping.")
                                continue
                            fn_obj      = functions_list[0]
                            fn_name     = fn_obj.get("name", "")
                            fn_id       = fn_obj.get("id", "")
                            fn_args_raw = fn_obj.get("arguments", "{}")
                            try:
                                fn_input = json.loads(fn_args_raw) if fn_args_raw else {}
                            except (json.JSONDecodeError, ValueError):
                                fn_input = {}
                            if not isinstance(fn_input, dict):
                                fn_input = {}
                            print(f"[TEXT-TEST] FUNCTION CALL: {fn_name} | id={fn_id} | args={fn_input}")

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
                                print(f"[TEXT-TEST] FunctionCallResponse sent: {result[:100]}")
                            except Exception as e:
                                print(f"[TEXT-TEST] FunctionCallResponse send error: {e}")

                except asyncio.CancelledError:
                    pass
                except Exception as e:
                    print(f"[TEXT-TEST] Agent receiver error: {e}")

            # --- Task 2: Receive text from client and inject to Deepgram ---
            async def receive_from_client() -> None:
                """
                Continuously reads text messages from the browser WebSocket.
                1. Parses JSON or plain text input from the client.
                2. Sends it to Deepgram agent via InjectUserMessage.
                3. Only exits when the client disconnects.
                """
                nonlocal session_active
                try:
                    while session_active:
                        try:
                            # Client sends JSON: {"text": "message here"}
                            raw_message: str = await websocket.receive_text()
                        except WebSocketDisconnect:
                            print("[TEXT-TEST] Client disconnected (WebSocketDisconnect)")
                            session_active = False
                            return
                        except Exception:
                            # Any receive error means client is gone
                            session_active = False
                            return

                        try:
                            client_msg: dict = json.loads(raw_message)
                            user_text: str = client_msg.get("text", "").strip()
                        except json.JSONDecodeError:
                            # If plain text is sent, use it directly
                            user_text = raw_message.strip()

                        if not user_text:
                            continue

                        print(f"[TEXT-TEST] User: {user_text}")
                        logger.log("USER", user_text)

                        # Forward user text to the Deepgram agent. The hotel flow
                        # has no server-side slot injection — the agent gathers all
                        # reservation fields itself and calls book_room.
                        inject_message: dict = {
                            "type": "InjectUserMessage",
                            "content": user_text
                        }
                        try:
                            await dg_agent.send(json.dumps(inject_message))
                        except websockets.exceptions.ConnectionClosed:
                            print("[TEXT-TEST] Cannot inject: Deepgram connection closed")
                            session_active = False
                            return
                        except Exception as e:
                            print(f"[TEXT-TEST] Error injecting message: {e}")
                            try:
                                await websocket.send_json({
                                    "role": "system",
                                    "content": f"Error sending message: {e}"
                                })
                            except Exception:
                                session_active = False
                                return

                except asyncio.CancelledError:
                    pass
                except Exception as e:
                    print(f"[TEXT-TEST] Client receiver error: {e}")

            # --- Task 3: Send periodic keepalive to Deepgram ---
            async def send_keepalive() -> None:
                """
                Sends a KeepAlive message to Deepgram every few seconds.
                1. Prevents the Deepgram agent from closing the connection due to inactivity.
                2. Uses the official KeepAlive message type from the Deepgram API.
                """
                try:
                    while session_active:
                        await asyncio.sleep(KEEPALIVE_INTERVAL_SECONDS)
                        if not session_active:
                            break
                        try:
                            keepalive_msg: dict = {"type": "KeepAlive"}
                            await dg_agent.send(json.dumps(keepalive_msg))
                        except websockets.exceptions.ConnectionClosed:
                            print("[TEXT-TEST] Keepalive failed: Deepgram connection closed")
                            break
                        except Exception as e:
                            print(f"[TEXT-TEST] Keepalive error: {e}")
                            break
                except asyncio.CancelledError:
                    pass

            # Run all three tasks concurrently.
            # We use ALL_COMPLETED instead of FIRST_COMPLETED so that
            # one task finishing does not immediately kill the others.
            # Instead, the session_active flag coordinates shutdown.
            tasks = [
                asyncio.create_task(receive_from_agent()),
                asyncio.create_task(receive_from_client()),
                asyncio.create_task(send_keepalive()),
            ]

            # Wait for the client receiver to finish (i.e., client disconnected)
            # or for the agent receiver to finish (i.e., Deepgram disconnected).
            # The keepalive task is secondary and should not drive shutdown.
            done, pending = await asyncio.wait(
                tasks, return_when=asyncio.FIRST_COMPLETED
            )

            # Signal all tasks to stop
            session_active = False

            # Give remaining tasks a moment to clean up, then cancel
            for task in pending:
                task.cancel()
                try:
                    await asyncio.wait_for(task, timeout=2.0)
                except (asyncio.CancelledError, asyncio.TimeoutError):
                    pass

    except websockets.exceptions.InvalidStatusCode as e:
        print(f"[TEXT-TEST] Deepgram auth error: {e}")
        try:
            await websocket.send_json({
                "role": "system",
                "content": f"Authentication error with Deepgram. Check your API key."
            })
        except Exception:
            pass
    except Exception as e:
        print(f"[TEXT-TEST] Connection error: {e}")
        try:
            await websocket.send_json({
                "role": "system",
                "content": f"Connection error: {e}"
            })
        except Exception:
            pass
    finally:
        # call.completed webhook (web chat -> call_sid is null per the contract)
        try:
            dispatch_call_completed({
                "caller_id": "web-chat",
                "to_number": "web-chat",
                "duration_seconds": int((datetime.utcnow() - session_start).total_seconds()),
                "booking_confirmed": bool(conversation_state.get("booking_confirmed")),
                "booking_id": conversation_state.get("booking_id"),
            }, None)
        except Exception as e:
            print(f"[TEXT-TEST] call.completed dispatch error: {e}")

        logger.log_event("Session ended")
        logger.close()
        print(f"[TEXT-TEST] Session ended. Log saved to: {logger.file_path}")
