# routers/brain.py
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
from services.agent_logic import process_agent_text_response

load_dotenv()

DEEPGRAM_API_KEY: str = os.getenv("DEEPGRAM_API_KEY", "")
AGENT_URL: str = "wss://agent.deepgram.com/v1/agent/converse"


def load_agent_config() -> dict:
    """
    Load the agent configuration from data/config.json and inject
    the current date/time into the system prompt.
    1. Reads the JSON config file.
    2. Appends a CONTEXT line with the current timestamp.

    Returns:
        The loaded and augmented config dict.
    """
    with open("data/config.json", "r") as f:
        agent_config: dict = json.load(f)

    # Inject current date and time so the agent knows "today"
    current_time: str = datetime.now().strftime("%A, %d %B %Y, %I:%M %p")
    agent_config["agent"]["think"]["prompt"] += f"\n\nCONTEXT: Today is {current_time}."
    print(f"Injecting time into prompt: {current_time}")

    return agent_config


async def process_audio_stream(websocket: WebSocket) -> None:
    """
    Main handler for a Twilio media stream WebSocket session.
    1. Connects to Deepgram Agent API with the loaded config.
    2. Runs two async tasks in parallel:
       - send_mic_audio: forwards Twilio audio to Deepgram
       - receive_agent_audio: forwards Deepgram responses back to Twilio
    3. Response text processing is delegated to the shared agent_logic module.
    """
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

    print(f"Connecting to: {AGENT_URL}")

    try:
        # extra_headers: auth token for Deepgram.
        # ping_interval/ping_timeout: built-in keepalive pings every 30 s so
        # the Deepgram connection does not idle-close during long phone calls.
        async with websockets.connect(
            AGENT_URL,
            extra_headers=headers,
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
                            if dg_agent.open:
                                await dg_agent.send(audio_bytes)
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

    except Exception as e:
        print(f"Connection Error: {e}")