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



# ==========================================
# CONFIGURATION
# ==========================================
import json
import base64
import asyncio
import websockets
from fastapi import WebSocket

DEEPGRAM_API_KEY = "4ca1fdbf693e32c4194bdcb0679dcf6d8b21910c"

# AGENT URL
AGENT_URL = "wss://agent.deepgram.com/v1/agent/converse"

async def process_audio_stream(websocket: WebSocket):
    clean_key = DEEPGRAM_API_KEY.strip()
    headers = { "Authorization": f"Token {clean_key}" }

    # 1. LOAD CONFIG
    try:
        with open("data/config.json", "r") as f:
            agent_config = json.load(f)
        print("Config loaded.")
    except Exception as e:
        print(f"Config Error: {e}")
        return

    print(f"Connecting to: {AGENT_URL}")

    try:
        async with websockets.connect(AGENT_URL, extra_headers=headers) as dg_agent:
            
            # 2. SEND CONFIG
            await dg_agent.send(json.dumps(agent_config))
            print("CONNECTION SUCCESS! Sarah is listening...")

            # --- SENDER ---
            async def send_mic_audio():
                try:
                    while True:
                        message = await websocket.receive_text()
                        data = json.loads(message)
                        if data['event'] == 'media':
                            audio_bytes = base64.b64decode(data['media']['payload'])
                            await dg_agent.send(audio_bytes)
                        elif data['event'] == 'stop':
                            break
                except Exception:
                    pass

            # --- RECEIVER ---
            async def receive_agent_audio():
                try:
                    while True:
                        response = await dg_agent.recv()
                        
                        if isinstance(response, bytes):
                            # AUDIO
                            media_message = {
                                "event": "media",
                                "media": {
                                    "payload": base64.b64encode(response).decode("utf-8")
                                }
                            }
                            await websocket.send_text(json.dumps(media_message))
                        else:
                            # TEXT
                            msg = json.loads(response)
                            if msg.get("type") == "ConversationText":
                                print(f"Sarah: {msg.get('content')}")
                            elif msg.get("type") == "UserStartedSpeaking":
                                print("USER: Speaking...")
                            elif msg.get("type") == "Error":
                                print(f"DEEPGRAM ERROR: {msg}")
                            
                except Exception as e:
                    print(f"Agent Connection Closed: {e}")

            await asyncio.gather(send_mic_audio(), receive_agent_audio())

    except Exception as e:
        print(f"Connection Error: {e}")