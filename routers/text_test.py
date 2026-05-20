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
    handle_user_slot_query,
    handle_date_selection_in_booking,
)
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
    
    context_str = f"\n\nCONTEXT: Today is {current_time}.\n\nCLINIC DATA:\n{clinic_data}"
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
        "appointment_date": None,
        "appointment_time": None,
        "reason": None,
        # Set to True once an appointment is successfully booked this session.
        # Prevents the agent from re-triggering a booking after farewell.
        "booking_confirmed": False,
        # Set to True when the last ConversationText message was a hidden JSON payload.
        # Used to suppress displaying raw JSON in the chat UI.
        "last_message_is_payload": False,
    }

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

                            # Process through shared agent logic
                            # (recap extraction, availability check, booking)
                            try:
                                conversation_state = await process_agent_text_response(
                                    content, conversation_state, dg_agent
                                )
                            except Exception as e:
                                print(f"[TEXT-TEST] Agent logic error: {e}")

                            # Forward the agent's text response to the client.
                            # Skip if the message was a hidden JSON payload (e.g. ready_to_book).
                            # Such payloads are processed by agent_logic and must not reach the UI.
                            is_payload: bool = conversation_state.get("last_message_is_payload", False)
                            if role == "assistant" and not is_payload:
                                try:
                                    await websocket.send_json({
                                        "role": "assistant",
                                        "content": content
                                    })
                                    logger.log("SARAH", content)
                                except Exception:
                                    # Client disconnected while we were sending
                                    session_active = False
                                    return

                                # Check if the agent just said goodbye.
                                # Give the browser a moment to display the farewell
                                # message, then send a session_ended signal so the
                                # UI can return to the welcome screen gracefully.
                                if conversation_state.get("session_should_end"):
                                    print("[TEXT-TEST] Farewell detected. Closing session.")
                                    logger.log_event("Session ended by agent farewell")
                                    await asyncio.sleep(1.5)
                                    try:
                                        await websocket.send_json({"role": "session_ended"})
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

                        # Step A: Explicit slot/date-availability query.
                        # Fires when user asks 'which slots are free' or 'which dates'.
                        # Queries DB and injects real data for Sarah to relay.
                        slot_query_detected: bool = await handle_user_slot_query(
                            user_text, conversation_state, dg_agent
                        )

                        if slot_query_detected:
                            print("[TEXT-TEST] Slot/date query handled via DB injection.")
                            continue

                        # Step B: Booking flow date selection.
                        # Fires when user mentions a date while we already have their name.
                        # Proactively fetches and injects real available slots for that date
                        # so Sarah tells the user the options rather than asking them to guess.
                        date_injected: bool = await handle_date_selection_in_booking(
                            user_text, conversation_state, dg_agent
                        )
                        # Do NOT stop here -- still send the user message so Sarah
                        # has full context (date + system slots data together).

                        # Step C: Normal path -- forward user text to Deepgram agent
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
        logger.log_event("Session ended")
        logger.close()
        print(f"[TEXT-TEST] Session ended. Log saved to: {logger.file_path}")
