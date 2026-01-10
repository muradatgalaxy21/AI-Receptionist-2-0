import os
import json
import base64
import asyncio
from dotenv import load_dotenv, find_dotenv
load_dotenv(find_dotenv())
# We ONLY import the Client. We do not import LiveOptions.
from deepgram import DeepgramClient

load_dotenv()

async def process_audio_stream(websocket):
    """
    The Brain: Handles the bi-directional audio stream.
    """
    print("Twilio connected to the Brain.")
    
    # Initialize to None for safety in 'finally' block
    dg_connection = None

    try:
        # 1. Initialize Deepgram
        # We leave this empty. It automatically looks for DEEPGRAM_API_KEY in .env
        deepgram = DeepgramClient()
        
        # Create a websocket connection to Deepgram
        dg_connection = deepgram.listen.asyncwebsocket.v("1")

        # --- EVENT HANDLERS ---

        # Handle Audio from AI
        async def on_audio(self, audio_data, **kwargs):
            encoded_audio = base64.b64encode(audio_data).decode("utf-8")
            response_message = {
                "event": "media",
                "streamSid": stream_sid,
                "media": {
                    "payload": encoded_audio
                }
            }
            await websocket.send_text(json.dumps(response_message))

        dg_connection.on("Audio", on_audio)

        # Handle Transcripts
        async def on_transcript(self, result, **kwargs):
            if result.channel and result.channel.alternatives:
                transcript = result.channel.alternatives[0].transcript
                if transcript:
                    print(f"User: {transcript}")

        dg_connection.on("Results", on_transcript)

        # --- CONNECT (The Fix) ---
        
        # We use a simple Dictionary instead of the LiveOptions class.
        # This bypasses the ImportError completely.
        options_dict = {
            "model": "nova-2",
            "encoding": "mulaw",
            "sample_rate": 8000,
            "smart_format": True
        }
        
        # Start connection using the dictionary
        if await dg_connection.start(options_dict) is False:
            print("Failed to connect to Deepgram")
            return

        # --- THE LOOP ---
        stream_sid = None

        while True:
            # Receive from Twilio
            message = await websocket.receive_text()
            data = json.loads(message)

            if data['event'] == 'start':
                stream_sid = data['start']['streamSid']
                print(f"Call started. ID: {stream_sid}")

            elif data['event'] == 'media':
                # Decode Base64 -> Raw Bytes
                audio_payload = base64.b64decode(data['media']['payload'])
                # Send to Deepgram
                await dg_connection.send(audio_payload)

            elif data['event'] == 'stop':
                print("Call ended.")
                break

    except Exception as e:
        print(f"Error in Brain Logic: {e}")
    finally:
        # Only finish if the connection was actually created
        if dg_connection:
            await dg_connection.finish()

