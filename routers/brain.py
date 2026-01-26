import json
import base64
import asyncio
import websockets
import os
from fastapi import WebSocket
from dotenv import load_dotenv
from services import tools

load_dotenv()

DEEPGRAM_API_KEY = os.getenv("DEEPGRAM_API_KEY")
AGENT_URL = "wss://agent.deepgram.com/v1/agent/converse"

async def process_audio_stream(websocket: WebSocket):
    conversation_state = {
        "first_name": None,
        "last_name": None,
        "appointment_date": None,
        "appointment_time": None,
        "reason": None
    }

    # Safety Check: Stop if key is missing
    if not DEEPGRAM_API_KEY:
        print("Error: DEEPGRAM_API_KEY is missing from .env file")
        return

    headers = { "Authorization": f"Token {DEEPGRAM_API_KEY}" }

    try:
        with open("data/config.json", "r") as f:
            agent_config = json.load(f)
    except Exception as e:
        print(f"Config Error: {e}")
        return

    stream_sid = None
    print(f"Connecting to: {AGENT_URL}")

    try:
        async with websockets.connect(AGENT_URL, extra_headers=headers, ping_interval=None) as dg_agent:
            await dg_agent.send(json.dumps(agent_config))
            print("CONNECTION SUCCESS! Sarah is listening...")

            async def send_mic_audio():
                nonlocal stream_sid
                try:
                    while True:
                        message = await websocket.receive_text()
                        data = json.loads(message)
                        if data['event'] == 'start':
                            stream_sid = data['start']['streamSid']
                        elif data['event'] == 'media':
                            audio_bytes = base64.b64decode(data['media']['payload'])
                            if dg_agent.open:
                                await dg_agent.send(audio_bytes)
                        elif data['event'] == 'stop':
                            break
                except Exception:
                    pass

            # --- RECEIVER (AI -> Phone) ---
            async def receive_agent_audio():
                try:
                    while True:
                        response = await dg_agent.recv()
                        
                        if isinstance(response, bytes):
                            if stream_sid:
                                media_message = {
                                    "event": "media",
                                    "streamSid": stream_sid,
                                    "media": {
                                        "payload": base64.b64encode(response).decode("utf-8")
                                    }
                                }
                                await websocket.send_text(json.dumps(media_message))
                        else:
                            # Text: Parse to decide filtering
                            msg = json.loads(response)
                            if msg.get("type") == "ConversationText":
                                content = msg.get("content")

                                try:
                                    payload = json.loads(content)

                                    if payload["type"] == "field_update":
                                        conversation_state[payload["field"]] = payload["value"]
                                        print(f"[STATE] {payload['field']} = {payload['value']}")

                                    elif payload["type"] == "ready_to_book":
                                        if all(conversation_state.values()):
                                            from services.database import book_appointment

                                            book_appointment(
                                                conversation_state["first_name"],
                                                conversation_state["last_name"],
                                                conversation_state["reason"],
                                                conversation_state["appointment_date"],
                                                conversation_state["appointment_time"]
                                            )

                                            print("APPOINTMENT CONFIRMED")

                                except json.JSONDecodeError:
                                    # Normal speech output
                                    print(f"Sarah: {content}")

                            elif msg.get("type") == "UserStartedSpeaking":
                                print("USER: Speaking...")
                            elif msg.get("type") == "Error":
                                print(f"DEEPGRAM ERROR: {msg}")
                            
                except Exception as e:
                    print(f"Agent Connection Closed: {e}")

            await asyncio.gather(send_mic_audio(), receive_agent_audio())

    except Exception as e:
        print(f"Connection Error: {e}")