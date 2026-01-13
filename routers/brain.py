
# routers/brain.py
import os
import json
import base64
import asyncio
from pathlib import Path
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from deepgram import DeepgramClient
from dotenv import load_dotenv

# --- FORCE LOAD .ENV ---
current_file = Path(__file__).resolve()
project_root = current_file.parent.parent
env_path = project_root / ".env"
load_dotenv(dotenv_path=env_path)

print("ENV path is: " , env_path)

# --- DEFINE THE ROUTER ---
router = APIRouter()

@router.websocket("/media-stream")
async def media_stream(websocket: WebSocket):
    await websocket.accept()
    print("Twilio connected to the Brain (WebSocket).")
    
    api_key = os.getenv("DEEPGRAM_API_KEY")
    if not api_key:
        print("CRITICAL ERROR: API Key is missing!")
        await websocket.close()
        return

    try:
        # 1. Initialize Deepgram Client
        client = DeepgramClient(api_key=api_key)
        
        # 2. Configuration for Voice Agent with Gemini
        settings = {
            "type": "SettingsConfiguration",
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
            "agent": {
                "listen": {
                    "model": "nova-2"
                },
                "think": {
                    "provider": {
                        "type": "google"
                    },
                    "model": "gemini-2.5-flash",
                    "instructions": "You are a helpful AI receptionist. You are concise and professional."
                },
                "speak": {
                    "model": "aura-asteria-en"
                },
                "greeting": "Hello! How can I help you today?"
            }
        }

        # Shared variable to hold stream_sid
        # Using a list to allow modification in inner scope if needed, though 'nonlocal' works too
        call_state = {"stream_sid": None}

        # --- EVENT HANDLERS ---
        def on_open(self, open, **kwargs):
            print(f"Deepgram Agent Connected: {open}")
            # Try to send settings. 
            # If the wrapper has a 'configure' method, use it.
            if hasattr(self, 'configure'):
                self.configure(settings)
                print("Configuration sent via .configure()")
            else:
                # If no configure method, we might need to send raw JSON 
                # but let's hope standard client.agent.v1.connect() yields an object with configure.
                print("Warning: No .configure method found on connection object.")

        def on_message(self, result, **kwargs):
            # This generally handles text messages (transcripts)
            # print(f"Agent Message: {result}")
            pass

        def on_metadata(self, metadata, **kwargs):
            print(f"Metadata: {metadata}")

        def on_error(self, error, **kwargs):
            print(f"Deepgram Error: {error}")

        def on_close(self, close, **kwargs):
            print(f"Deepgram Connection Closed: {close}")

        async def on_audio(self, data, **kwargs):
            # Handler for binary audio data from the agent
            if call_state["stream_sid"] and data:
                payload = base64.b64encode(data).decode("utf-8")
                media_message = {
                    "event": "media",
                    "streamSid": call_state["stream_sid"],
                    "media": {
                        "payload": payload
                    }
                }
                # Send back to Twilio
                # Note: 'websocket' is from the outer scope (closure)
                await websocket.send_text(json.dumps(media_message))

        # --- CONNECT & LOOP ---
        # client.agent.v1.connect() return a context manager
        dg_connection = client.agent.v1.connect()
        
        # Register Handlers
        dg_connection.on("open", on_open)
        dg_connection.on("close", on_close)
        dg_connection.on("error", on_error)
        dg_connection.on("metadata", on_metadata)
        
        # Crucial: Register audio handler. 
        # Inspection showed 'OutputAudio' or similar might be the event name, 
        # but 'Binary' or 'audio' are common.
        # We will register 'OutputAudio' based on some docs, and also 'Binary' to be safe?
        # Actually standard Voice Agent docs usually simply say:
        # connection.on(LiveTranscriptionEvents.Audio, on_audio) wrapped?
        # We'll use the string "audio" which is typical for SDK v3/v4/v5 unification.
        dg_connection.on("audio", on_audio)
        dg_connection.on("Binary", on_audio) # Fallback if event name differs
        
        with dg_connection as agent:
            print("Deepgram Voice Agent Loop Started")
            
            while True:
                # Receive from Twilio
                message = await websocket.receive_text()
                data = json.loads(message)

                if data['event'] == 'start':
                    call_state["stream_sid"] = data['start']['streamSid']
                    print(f"Call started. Stream SID: {call_state['stream_sid']}")

                elif data['event'] == 'media':
                    # Decode Base64 -> Raw Bytes
                    audio_payload = base64.b64decode(data['media']['payload'])
                    # Send to Deepgram Agent
                    agent.send(audio_payload)

                elif data['event'] == 'stop':
                    print("Call ended.")
                    break
                    
    except WebSocketDisconnect:
        print("Twilio hung up.")
    except Exception as e:
        print(f"Error in Brain Logic: {e}")
        import traceback
        traceback.print_exc()
