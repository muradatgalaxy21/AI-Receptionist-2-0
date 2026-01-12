import os
import json
import base64
import asyncio
import websockets
from dotenv import load_dotenv

# --- 1. SETUP & CREDENTIALS ---
current_dir = os.path.dirname(os.path.abspath(__file__))
env_path = os.path.join(current_dir, '..', '.env')
load_dotenv(env_path)

API_KEY = "9c81094c8b7be49dfab223260f70dd865c4cffe0" 

print(f"🔒 BRAIN IS USING KEY: {API_KEY[:5]}... (Length: {len(API_KEY)})")
print("------------------------------------------------")
if API_KEY:
    print(f"DEBUG: Key found! It starts with: {API_KEY[:5]}...")
else:
    print("DEBUG: API_KEY is missing! Check .env file path.")
print("------------------------------------------------")

# --- 2. CONFIG LOADER ---
def load_project_config():
    base_dir = os.path.join(current_dir, '..', 'data')
    with open(os.path.join(base_dir, 'data.json'), 'r') as f:
        clinic_data = json.load(f)
    with open(os.path.join(base_dir, 'config.json'), 'r') as f:
        config = json.load(f)
    return config

# --- 3. THE BRAIN LOGIC  ---
async def process_audio_stream(websocket):
    print("Twilio connected to the Brain.")
    
    if not API_KEY:
        print("ERROR: No API Key found.")
        return


    DEEPGRAM_URL = (
        f"wss://api.deepgram.com/v1/listen"
        f"?encoding=mulaw"
        f"&sample_rate=8000"
        f"&model=nova-2"
        f"&smart_format=true"
        f"&token={API_KEY}" 
    )

    try:
        async with websockets.connect(DEEPGRAM_URL, ping_interval=None) as dg_socket:
            print("Connected to Deepgram (Directly)")

            # --- SENDER: Phone -> Deepgram ---
            async def send_audio():
                stream_sid = None
                try:
                    while True:
                        # Receive audio from Twilio/Test
                        message = await websocket.receive_text()
                        data = json.loads(message)

                        if data['event'] == 'start':
                            stream_sid = data['start']['streamSid']
                            print(f"Call started. ID: {stream_sid}")
                        
                        elif data['event'] == 'media':
                            # Extract audio and send to Deepgram
                            audio_payload = base64.b64decode(data['media']['payload'])
                            await dg_socket.send(audio_payload)
                        
                        elif data['event'] == 'stop':
                            print("Call ended.")
                            # Send empty frame to close Deepgram stream gracefully
                            await dg_socket.send(b"")
                            break
                except Exception as e:
                    print(f"Error sending audio: {e}")

            # --- RECEIVER: Deepgram -> Phone ---
            async def receive_transcript():
                try:
                    while True:
                        # Listen for text from Deepgram
                        response = await dg_socket.recv()
                        data = json.loads(response)
                        
                        # Extract transcript
                        if "channel" in data:
                            alternatives = data["channel"]["alternatives"]
                            if alternatives:
                                transcript = alternatives[0]["transcript"]
                                if transcript:
                                    print(f"User: {transcript}")
                                    
                                    # Send back to Test Script/Twilio
                                    response_json = json.dumps({
                                        "event": "transcription", 
                                        "text": transcript
                                    })
                                    await websocket.send_text(response_json)
                except Exception as e:
                    pass

            # Run Sender and Receiver at the same time
            await asyncio.gather(send_audio(), receive_transcript())

    except Exception as e:
        print(f"Connection Error: {e}")