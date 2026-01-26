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
        "last_name":  None,
        "appointment_date": None,
        "appointment_time": None,
        "reason": None
    }
    FIELD_ORDER = [
        "first_name",
        "last_name",
        "appointment_date",
        "appointment_time",
        "reason"
    ]

    def get_next_missing_field(state):
        for field in FIELD_ORDER:
            if not state[field]:
                return field
        return None

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

            import time

            # --- SHARED STATE FOR FILTERING ---
            shared_state = {
                "should_speak": True,
                "first_byte_received": False
            }
            audio_queue = asyncio.Queue()

            # --- LISTENER (Deepgram -> Filter -> Queue/Print) ---
            async def socket_listener():
                try:
                    while True:
                        response = await dg_agent.recv()
                        
                        if isinstance(response, bytes):
                            # Audio: Only queue if we are allowed to speak
                            if shared_state["should_speak"]:
                                await audio_queue.put((time.time(), response))
                        else:
                            # Text: Parse to decide filtering
                            msg = json.loads(response)
                            msg_type = msg.get("type")

                            if msg_type == "ConversationText":
                                content = msg.get("content")
                                
                                try:
                                    payload = json.loads(content)
                                    # If it's a structural update, MUTE audio
                                    if payload["type"] in ["field_update", "ready_to_book"]:
                                        shared_state["should_speak"] = False
                                        
                                        # Process State Logic
                                        if payload["type"] == "field_update":
                                            field = payload["field"]
                                            value = payload["value"]
                                            conversation_state[field] = value
                                            print(f"[STATE] {field} = {value}")

                                            next_field = get_next_missing_field(conversation_state)
                                            if next_field:
                                                 await dg_agent.send(json.dumps({
                                                    "type": "assistant",
                                                    "content": f"Please ask the user for their {next_field.replace('_', ' ')}."
                                                }))

                                        elif payload["type"] == "ready_to_book":
                                            if all(conversation_state.values()):
                                                from services.database import book_appointment
                                                book_appointment(
                                                    conversation_state["first_name"],
                                                    conversation_state["last_name"],
                                                    conversation_state["appointment_date"],
                                                    conversation_state["appointment_time"],
                                                    conversation_state["reason"],
                                                )

                                    else:
                                        # JSON but maybe valid speech? Rare. Unmute.
                                        shared_state["should_speak"] = True

                                except json.JSONDecodeError:
                                    # Normal speech text -> Unmute
                                    shared_state["should_speak"] = True
                                    print(f"Sarah: {content}")

                            elif msg_type == "UserStartedSpeaking":
                                print("USER: Speaking...")
                                # Reset mute state
                                shared_state["should_speak"] = True
                                # Reset Delay Logic
                                shared_state["first_byte_received"] = False
                                
                            elif msg_type == "Error":
                                print(f"DEEPGRAM ERROR: {msg}")

                except Exception as e:
                    print(f"Listener Error: {e}")

            # --- SENDER (Queue -> Phone) ---
            async def audio_sender():
                nonlocal stream_sid
                last_user_start_time = time.time()
                
                while True:
                    # BLOCK here until audio is available
                    timestamp, audio_chunk = await audio_queue.get()
                    
                    # Logic: If we receive a chunk, we process delay
                    if not shared_state["first_byte_received"]:
                        # Determine if this is a "new" turn. 
                        # Crude heuristic: if queue was empty for a while. 
                        # Better: Use the timestamp vs last_user_start time we need to track.
                        # Since we cannot easily access 'UserStartedSpeaking' time here accurately without shared state,
                        # let's share 'last_user_speaking_time' via outer scope var if possible or simple delay for every First Byte after a pause.
                        
                        latency = time.time() - timestamp # This timestamp is when we received it from DG
                        # Actually we want time since user spoke.
                        # Let's simplify: Always delay 1s on the first chunk of a "sentence".
                        
                        print(f"Audio received. Waiting 1 second...")
                        await asyncio.sleep(1.0)
                        shared_state["first_byte_received"] = True

                    # Check stream_sid
                    if stream_sid:
                        media_message = {
                            "event": "media",
                            "streamSid": stream_sid,
                            "media": {
                                "payload": base64.b64encode(audio_chunk).decode("utf-8")
                            }
                        }
                        await websocket.send_text(json.dumps(media_message))
                    
                    audio_queue.task_done()
                    
                    # If queue is empty, reset first_byte_received? 
                    # No, that might reset mid-sentence. 
                    # We rely on 'UserStartedSpeaking' to reset 'first_byte_received' usually.
                    # We need to bridge 'UserStartedSpeaking' to here.
            
            # Since we can't easily signal 'first_byte_received = False' from listener to sender without a Event,
            # Let's update sender to read a shared flag 'user_interrupted'.
            
            await asyncio.gather(send_mic_audio(), socket_listener(), audio_sender())

    except Exception as e:
        print(f"Connection Error: {e}")