# import os
# import json
# import base64
# import asyncio
# import websockets
# from fastapi import APIRouter, WebSocket

# # Your working key
# API_KEY = "4ca1fdbf693e32c4194bdcb0679dcf6d8b21910c"

# async def process_audio_stream(websocket: WebSocket):
#     clean_key = API_KEY.strip()
    
#     # 1. Define Headers (The Safe Way)
#     # This hides the key from your router/firewall
#     headers = {
#         "Authorization": f"Token {clean_key}"
#     }

#     # 2. Define URL (No Key here)
#     DEEPGRAM_URL = (
#         f"wss://api.deepgram.com/v1/listen"
#         f"?encoding=mulaw"
#         f"&sample_rate=8000"
#         f"&model=nova-2"
#         f"&smart_format=true"
#     )

#     print("Connecting to Deepgram (Header Auth)...")

#     try:
#         # 3. Connect using extra_headers
#         async with websockets.connect(DEEPGRAM_URL, extra_headers=headers) as dg_socket:
#             print("SUCCESS: Connected to Deepgram!")
#             print("Waiting for you to speak...")

#             # --- SENDER: Phone -> Deepgram ---
#             async def send_mic_audio():
#                 try:
#                     while True:
#                         message = await websocket.receive_text()
#                         data = json.loads(message)

#                         if data['event'] == 'media':
#                             # Send audio payload to Deepgram
#                             audio_bytes = base64.b64decode(data['media']['payload'])
#                             await dg_socket.send(audio_bytes)
                        
#                         elif data['event'] == 'stop':
#                             print("Call ended.")
#                             await dg_socket.send(b"")
#                             break
#                 except Exception as e:
#                     print(f"Error sending audio: {e}")

#             # --- RECEIVER: Deepgram -> Terminal ---
#             async def get_transcription():
#                 try:
#                     while True:
#                         response = await dg_socket.recv()
#                         data = json.loads(response)

#                         if "channel" in data:
#                             alternatives = data["channel"]["alternatives"]
#                             if alternatives:
#                                 transcript = alternatives[0]["transcript"]
#                                 if transcript:
#                                     # Print what you say in real-time
#                                     print(f"🗣️ YOU: {transcript}")
#                 except Exception as e:
#                     print(f"Error receiving: {e}")

#             await asyncio.gather(send_mic_audio(), get_transcription())

#     except Exception as e:
#         print(f"Connection Error: {e}")



import json
import base64
import asyncio
import websockets
import os
from fastapi import WebSocket
from dotenv import load_dotenv

# Load environment variables from the .env file
load_dotenv()

# ==========================================
# CONFIGURATION
# ==========================================
# Now we get the key from the environment instead of hardcoding it
DEEPGRAM_API_KEY = os.getenv("DEEPGRAM_API_KEY")

# URL that works for your account
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

    # 1. LOAD CONFIG
    try:
        with open("data/config.json", "r") as f:
            agent_config = json.load(f)
        print("Config loaded from data/config.json")
    except Exception as e:
        print(f"Config Error: {e}")
        return

    # Variable to track the specific call ID
    stream_sid = None

    print(f"Connecting to: {AGENT_URL}")

    try:
        async with websockets.connect(AGENT_URL, extra_headers=headers) as dg_agent:
            
            # 2. SEND CONFIG
            await dg_agent.send(json.dumps(agent_config))
            print("CONNECTION SUCCESS! Sarah is listening...")

            # --- SENDER (Phone -> AI) ---
            async def send_mic_audio():
                nonlocal stream_sid
                try:
                    while True:
                        message = await websocket.receive_text()
                        data = json.loads(message)
                        
                        if data['event'] == 'start':
                            stream_sid = data['start']['streamSid']
                            print(f"Call Started. Stream SID: {stream_sid}")
                        
                        elif data['event'] == 'media':
                            audio_bytes = base64.b64decode(data['media']['payload'])
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