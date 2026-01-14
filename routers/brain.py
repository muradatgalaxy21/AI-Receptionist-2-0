import os
import json
import base64
import asyncio
import websockets
from fastapi import WebSocket
from dotenv import load_dotenv

# Load API Key
load_dotenv(r"E:\AI_and_Beyond\AI-Receptionist\ai-receptionist\.env")
API_KEY = os.getenv("DEEPGRAM_API_KEY")

async def process_audio_stream(twilio_ws: WebSocket):
    # 1. Load User Configuration
    try:
        with open(r'E:\AI_and_Beyond\AI-Receptionist\ai-receptionist\config.json') as f:
            config_data = json.load(f)
    except FileNotFoundError:
        print("Error: config.json not found.")
        return

    # 2. Setup Queues
    audio_queue = asyncio.Queue()
    streamsid_queue = asyncio.Queue()

    # 3. Connect to Deepgram
    DEEPGRAM_URL = "wss://agent.deepgram.com/v1/agent/converse"
    
    if not API_KEY:
        print("Error: DEEPGRAM_API_KEY is missing.")
        return

    try:
        # KeepAlive settings prevent random disconnects
        async with websockets.connect(
            DEEPGRAM_URL, 
            subprotocols=["token", API_KEY],
            ping_interval=5, 
            ping_timeout=20
        ) as deepgram_ws:
            
            print("Connected to Deepgram Voice Agent")

            # 4. Handshake (Simple & Clean)
            # We do NOT manually inject 'barge_in'. We trust your config.json + defaults.
            settings_payload = {
                "type": "Settings",
                "audio": {
                    "input": {
                        "encoding": "mulaw",
                        "sample_rate": 8000
                    },
                    "output": {
                        "encoding": "mulaw",
                        "sample_rate": 8000,
                        "container": "none"
                    }
                },
                "agent": config_data.get("agent")
            }
            
            await deepgram_ws.send(json.dumps(settings_payload))

            # --- TASK 1: Twilio Receiver (Input) ---
            async def twilio_receiver():
                print("Started Twilio Receiver")
                try:
                    while True:
                        message = await twilio_ws.receive_text()
                        data = json.loads(message)

                        if data['event'] == 'start':
                            sid = data['start']['streamSid']
                            print(f"Call Started: {sid}")
                            streamsid_queue.put_nowait(sid)
                        
                        elif data['event'] == 'media':
                            media = data['media']
                            
                            # CRITICAL FIX: The "Filter"
                            # We ONLY send audio when the HUMAN speaks ('inbound').
                            # We IGNORE audio when the AI speaks ('outbound').
                            if media['track'] == 'inbound':
                                chunk = base64.b64decode(media['payload'])
                                audio_queue.put_nowait(chunk)
                        
                        elif data['event'] == 'stop':
                            print("Call Ended.")
                            break

                except Exception as e:
                    print(f"Twilio Receiver Error: {e}")

            # --- TASK 2: Deepgram Sender (Uplink) ---
            async def deepgram_sender():
                print("Started Deepgram Sender")
                try:
                    while True:
                        chunk = await audio_queue.get()
                        await deepgram_ws.send(chunk)
                except Exception as e:
                    pass

            # --- TASK 3: Deepgram Receiver (Downlink) ---
            async def deepgram_receiver():
                print("Started Deepgram Receiver")
                streamsid = await streamsid_queue.get()
                
                try:
                    async for message in deepgram_ws:
                        # Case A: Audio Data (Agent Voice)
                        if isinstance(message, bytes):
                            audio_b64 = base64.b64encode(message).decode("ascii")
                            media_message = {
                                "event": "media",
                                "streamSid": streamsid,
                                "media": {"payload": audio_b64}
                            }
                            await twilio_ws.send_text(json.dumps(media_message))
                        
                        # Case B: Text Events (Control)
                        elif isinstance(message, str):
                            decoded = json.loads(message)
                            msg_type = decoded.get("type")

                            if msg_type == "UserStartedSpeaking":
                                # This handles the interruption automatically
                                clear_msg = { "event": "clear", "streamSid": streamsid }
                                await twilio_ws.send_text(json.dumps(clear_msg))
                            
                            elif msg_type == "Welcome":
                                print("Agent Ready!")
                                
                            elif msg_type == "Error":
                                print(f"Deepgram Error: {decoded}")

                except Exception as e:
                    print(f"Deepgram Receiver Error: {e}")

            # Run all tasks
            await asyncio.gather(
                twilio_receiver(),
                deepgram_sender(),
                deepgram_receiver()
            )

    except Exception as e:
        print(f"Connection Error: {e}")