# routers/brain.py
import json
import base64
import asyncio
import websockets
import os
import re
from datetime import datetime
from fastapi import WebSocket
from dotenv import load_dotenv
from services.database import book_appointment
from services.tools import check_availability, parse_date, get_available_slots_tool

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

    if not DEEPGRAM_API_KEY:
        print("Error: DEEPGRAM_API_KEY is missing from .env file")
        return

    headers = { "Authorization": f"Token {DEEPGRAM_API_KEY}" }

    # Load Config
    try:
        with open("data/config.json", "r") as f:
            agent_config = json.load(f)

        # INJECT CURRENT DATE & TIME
        current_time = datetime.now().strftime("%A, %d %B %Y, %I:%M %p")
        agent_config["agent"]["think"]["prompt"] += f"\n\nCONTEXT: Today is {current_time}."
        print(f"Injecting time into prompt: {current_time}")
    except Exception as e:
        print(f"Config Error: {e}")
        return

    print(f"Connecting to: {AGENT_URL}")

    try:
        async with websockets.connect(AGENT_URL, extra_headers=headers, ping_interval=None) as dg_agent:
            await dg_agent.send(json.dumps(agent_config))
            print("CONNECTION SUCCESS! Sarah is listening...")

            stream_sid = None

            # --- SENDER (Phone -> AI) ---
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
                        
                        # 1. Handle Audio (Binary)
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
                        
                        # 2. Handle Text (JSON)
                        else:
                            msg = json.loads(response)
                            
                            # --- A. Normal Speech (The user hears this) ---
                            if msg.get("type") == "ConversationText":
                                content = msg.get("content")
                                print(f"Sarah: {content}") # Log what she says

                                # --- NEW: TEXT EXTRACTION LOGIC (The Fix) ---
                                # We watch for the specific "To recap" message format
                                if "First Name:" in content and "Last Name:" in content:
                                    print("--> DETECTED RECAP! Extracting data from text...")
                                    
                                    # Use Regex to find values after the colons
                                    # This looks for "- Key: Value" patterns
                                    first_name_match = re.search(r"First Name:\s*(.*)", content)
                                    last_name_match = re.search(r"Last Name:\s*(.*)", content)
                                    date_match = re.search(r"Appointment Date:\s*(.*)", content)
                                    time_match = re.search(r"Appointment Time:\s*(.*)", content)
                                    reason_match = re.search(r"Reason:\s*(.*)", content)

                                    if first_name_match: conversation_state["first_name"] = first_name_match.group(1).strip()
                                    if last_name_match: conversation_state["last_name"] = last_name_match.group(1).strip()
                                    if date_match: conversation_state["appointment_date"] = date_match.group(1).strip()
                                    if time_match: conversation_state["appointment_time"] = time_match.group(1).strip()
                                    if reason_match: conversation_state["reason"] = reason_match.group(1).strip()

                                    print(f"--> STATE UPDATED FROM TEXT: {conversation_state}")
                                
                                # Check for hidden JSON payloads (Keep this just in case)
                                try:
                                    payload = json.loads(content)
                                    if payload.get("type") == "ready_to_book":
                                        print("[EVENT] Ready to book signal received.")
                                        
                                        if all(conversation_state.values()):
                                            # --- CHECK AVAILABILITY ---
                                            appt_date = conversation_state["appointment_date"]
                                            appt_time = conversation_state["appointment_time"]
                                            
                                            is_available = check_availability(appt_date, appt_time)

                                            if is_available:
                                                print("--> All fields present & Slot Available. Booking now...")
                                                # Use parsed date for storage consistency
                                                real_date = parse_date(appt_date)
                                                
                                                success = book_appointment(
                                                    conversation_state["first_name"],
                                                    conversation_state["last_name"],
                                                    real_date,
                                                    appt_time,
                                                    conversation_state["reason"]
                                                )
                                                if success:
                                                    print("✅ APPOINTMENT BOOKED!")
                                                    await asyncio.sleep(3) # Let her finish speaking
                                                    break # End call
                                            else:
                                                print("--> SLOT UNAVAILABLE. Reporting back to Agent...")
                                                
                                                # 1. Get Available Slots
                                                free_slots = get_available_slots_tool(appt_date)
                                                free_slots_str = ", ".join(free_slots) if free_slots else "No slots available"

                                                # 2. Update Prompt via Settings (Safer than direct text injection)
                                                # We append the instruction to the CURRENT prompt context
                                                original_prompt = agent_config["agent"]["think"]["prompt"]
                                                
                                                # Remove previous system injections to avoid clutter (optional, but good practice)
                                                clean_prompt = original_prompt.split("SYSTEM UPDATE:")[0].strip()
                                                
                                                new_prompt = clean_prompt + f"\n\nSYSTEM UPDATE: The user requested {appt_date} at {appt_time}, but it is BOOKED. You MUST apologize and offer these available times: {free_slots_str}. Ask which one they prefer."
                                                
                                                settings_update = {
                                                    "type": "Settings",
                                                    "agent": {
                                                        "think": {
                                                            "prompt": new_prompt
                                                        }
                                                    }
                                                }
                                                
                                                await dg_agent.send(json.dumps(settings_update))
                                                print(f"--> Updated Agent Prompt with available slots: {free_slots_str}")
                                                
                                                # Reset Date/Time in state so we can collect new ones
                                                conversation_state["appointment_time"] = None
                                                # Keep date to avoid re-asking? No, asking "What time?" implies date is same. 
                                                # But if they want to change date, we might want to clear it?
                                                # Let's keep date for now, just clear time.
                                        else:
                                            print("--> Missing fields. Cannot book yet.")
                                except json.JSONDecodeError:
                                    pass # Not a JSON hidden message, just normal text

                except Exception as e:
                    print(f"Agent Receiver Error: {e}")

            # Run both tasks
            tasks = [asyncio.create_task(send_mic_audio()), asyncio.create_task(receive_agent_audio())]
            done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            for task in pending: task.cancel()

    except Exception as e:
        print(f"Connection Error: {e}")