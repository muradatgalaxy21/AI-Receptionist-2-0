# routers/brain.py
from datetime import datetime
# Handles the Twilio media stream WebSocket connection.
# Bridges audio between Twilio (phone) and the Deepgram Agent API.
# Response processing (recap extraction, booking) is delegated to
# services.agent_logic so it can be shared with the text-test path.

import json
import base64
import asyncio
import websockets
import os
from datetime import datetime
from fastapi import WebSocket
from dotenv import load_dotenv
from services.agent_logic import process_agent_text_response, handle_user_slot_query

load_dotenv()

DEEPGRAM_API_KEY: str = os.getenv("DEEPGRAM_API_KEY", "")
AGENT_URL: str = "wss://agent.deepgram.com/v1/agent/converse"


def load_agent_config() -> dict:
    """
    Load the agent configuration from data/config.json and inject
    the current date/time and clinic data into the system prompt.
    """
    with open("data/config.json", "r") as f:
        agent_config: dict = json.load(f)

    with open("data/data.json", "r") as f:
        clinic_data: str = f.read()

    # Inject current date and time so the agent knows "today"
    current_time: str = datetime.now().strftime("%A, %d %B %Y, %I:%M %p")
    
    # Append context and clinic data
    context_str = f"\n\nCONTEXT: Today is {current_time}.\n\nCLINIC DATA:\n{clinic_data}"
    agent_config["agent"]["think"]["prompt"] += context_str
    print(f"Injecting time and clinic data into prompt.")

    return agent_config


async def process_audio_stream(websocket: WebSocket) -> None:
    """
    Handles a Twilio media stream WebSocket session and logs call details after completion.

    Main handler for a Twilio media stream WebSocket session.
    1. Connects to Deepgram Agent API with the loaded config.
    2. Runs two async tasks in parallel:
       - send_mic_audio: forwards Twilio audio to Deepgram
       - receive_agent_audio: forwards Deepgram responses back to Twilio
    3. Response text processing is delegated to the shared agent_logic module.
    """
    # Record start time of the call for duration calculation
    start_time: datetime = datetime.utcnow()

    conversation_state: dict = {
        "first_name": None,
        "last_name": None,
        "appointment_date": None,
        "appointment_time": None,
        "reason": None
    }

    if not DEEPGRAM_API_KEY:
        print("Error: DEEPGRAM_API_KEY is missing from .env file")
        return

    headers: dict = {"Authorization": f"Token {DEEPGRAM_API_KEY}"}

    # Load Config
    try:
        agent_config: dict = load_agent_config()
    except Exception as e:
        print(f"Config Error: {e}")
        return

    # Pass auth token in URL — avoids any websockets version header issues
    agent_url_with_auth = f"{AGENT_URL}?token={DEEPGRAM_API_KEY}"
    print(f"Connecting to Deepgram Agent (websockets=={websockets.__version__})")

    try:
        async with websockets.connect(
            agent_url_with_auth,
            ping_interval=30,
            ping_timeout=60,
        ) as dg_agent:
            await dg_agent.send(json.dumps(agent_config))
            print("CONNECTION SUCCESS! Sarah is listening...")

            stream_sid: str = None

            # --- SENDER (Phone -> AI) ---
            # Reads audio frames from Twilio WebSocket and forwards to Deepgram
            async def send_mic_audio() -> None:
                nonlocal stream_sid
                try:
                    while True:
                        message: str = await websocket.receive_text()
                        data: dict = json.loads(message)
                        if data["event"] == "start":
                            stream_sid = data["start"]["streamSid"]
                        elif data["event"] == "media":
                            # Decode base64 audio payload from Twilio
                            audio_bytes: bytes = base64.b64decode(
                                data["media"]["payload"]
                            )
                            try:
                                await dg_agent.send(audio_bytes)
                            except Exception:
                                pass
                        elif data["event"] == "stop":
                            break
                except Exception:
                    pass

            # --- RECEIVER (AI -> Phone) ---
            # Reads responses from Deepgram and sends audio back to Twilio
            async def receive_agent_audio() -> None:
                nonlocal conversation_state
                try:
                    while True:
                        response = await dg_agent.recv()

                        # 1. Handle Audio (Binary) -- forward to Twilio
                        if isinstance(response, bytes):
                            if stream_sid:
                                media_message: dict = {
                                    "event": "media",
                                    "streamSid": stream_sid,
                                    "media": {
                                        "payload": base64.b64encode(
                                            response
                                        ).decode("utf-8")
                                    }
                                }
                                await websocket.send_text(
                                    json.dumps(media_message)
                                )

                        # 2. Handle Text (JSON) -- process via shared logic
                        else:
                            msg: dict = json.loads(response)

                            if msg.get("type") == "ConversationText":
                                content: str = msg.get("content", "")
                                # Delegate all response processing to the shared module
                                conversation_state = await process_agent_text_response(
                                    content, conversation_state, dg_agent
                                )

                except Exception as e:
                    print(f"Agent Receiver Error: {e}")

            # Run both tasks concurrently
            tasks = [
                asyncio.create_task(send_mic_audio()),
                asyncio.create_task(receive_agent_audio())
            ]

            done, pending = await asyncio.wait(
                tasks, return_when=asyncio.FIRST_COMPLETED
            )
            for task in pending:
                task.cancel()

            # Calculate call metrics and log them
            from services.call_logger import append_call_log
            import uuid
            end_time: datetime = datetime.utcnow()
            call_duration: float = (end_time - start_time).total_seconds()
            
            # Extract patient name if available
            patient_name: str = ""
            if conversation_state.get("first_name") and conversation_state.get("last_name"):
                patient_name = f"{conversation_state['first_name']} {conversation_state['last_name']}"
                
            # Determine intent based on whether a booking was confirmed
            intent: str = "Booking" if conversation_state.get("booking_confirmed") else "FAQ"
            status: str = "Confirmed" if conversation_state.get("booking_confirmed") else "Follow-up Needed"
            
            # Placeholder estimated value – could be derived from business logic
            estimated_value: float = 100.0 if conversation_state.get("booking_confirmed") else 0.0
            
            # Recording URL – TBD, placeholder for now
            recording_url: str = ""
            # Caller ID – not available in current context, set to unknown
            caller_id: str = "unknown"
            # Timestamp for CSV entry
            timestamp: str = end_time.isoformat()
            
            # Append to CSV
            append_call_log(
                timestamp=timestamp,
                caller_id=caller_id,
                patient_name=patient_name,
                call_duration=call_duration,
                intent=intent,
                summary=conversation_state.get("last_summary", ""),
                status=status,
                estimated_value=estimated_value,
                recording_url=recording_url,
            )

    except Exception as e:
        print(f"Connection Error: {e}")