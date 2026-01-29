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
                                    print(f"DEBUG: Checking regex matches on content: {content}")
                                    first_name_match = re.search(r"First Name:\s*(.*?)(?:$|\n|\.|,)", content)
                                    last_name_match = re.search(r"Last Name:\s*(.*?)(?:$|\n|\.|,)", content)
                                    # Flexible matching: Handles "Appointment Date" OR just "Date"
                                    date_match = re.search(r"(?:Appointment )?Date:\s*(.*?)(?:$|\n|\.|,)", content)
                                    # Flexible matching: Handles "Appointment Time" OR just "Time"
                                    time_match = re.search(r"(?:Appointment )?Time:\s*(.*?)(?:$|\n|\.|,)", content)
                                    reason_match = re.search(r"Reason:\s*(.*?)(?:$|\n|\.|,)", content)

                                    print(f"DEBUG: Matches -> Name: {first_name_match}, Date: {date_match}, Time: {time_match}")

                                    if first_name_match: conversation_state["first_name"] = first_name_match.group(1).strip()
                                    if last_name_match: conversation_state["last_name"] = last_name_match.group(1).strip()
                                    if date_match: conversation_state["appointment_date"] = date_match.group(1).strip()
                                    if time_match: conversation_state["appointment_time"] = time_match.group(1).strip()
                                    if reason_match: conversation_state["reason"] = reason_match.group(1).strip()

                                    print(f"--> STATE UPDATED FROM TEXT: {conversation_state}")

                                # --- NEW: EARLY AVAILABILITY CHECK ---
                                # Check availability immediately when the specific time is confirmed/recorded
                                if "I will record the appointment time as" in content:
                                    # We need to make sure we have both date and time
                                    # Sometimes date comes earlier. State should have it.
                                    current_date = conversation_state.get("appointment_date")
                                    # Extract the time specifically from this utterance to be safe, or fallback to state
                                    # The state text extraction overhead might happen slightly after this line due to order? 
                                    # Let's rely on regex here for instant precision
                                    time_match_instant = re.search(r"I will record the appointment time as\s+(.*?)(?:$|\n|\.|,)", content)
                                    print(f"DEBUG: Instant Time Match: {time_match_instant}")
                                    current_time = time_match_instant.group(1).strip() if time_match_instant else conversation_state.get("appointment_time")
                                    
                                    if current_date and current_time:
                                        print(f"--> EARLY CHECK DETECTED for {current_date} at {current_time} (State: {conversation_state})")
                                        is_available_early = check_availability(current_date, current_time)
                                        print(f"DEBUG: check_availability result: {is_available_early}")
                                        
                                        if not is_available_early:
                                            print(f"DEBUG: Entering Early Warning Block. Current Date: {current_date}, Time: {current_time}")
                                            print("--> ⚠️ EARLY WARNING: SLOT TAKEN. Interrupting Agent...")
                                            
                                            # 1. Get alternatives
                                            free_slots = get_available_slots_tool(current_date)
                                            free_slots_str = ", ".join(free_slots) if free_slots else "No slots available"
                                            
                                            # 2. INJECT SYSTEM MESSAGE (Forces immediate reaction)
                                            # We pretend to be a "System" signal telling the agent to correct itself.
                                            interrupt_message = {
                                                "type": "ConversationText",
                                                "role": "user", # Using 'user' role often forces a reply better than system in some protocols, or just use a strong prompt injection
                                                "content": f"[SYSTEM ALERT]: The time {current_time} on {current_date} is UNAVAILABLE. You must STOP and inform the user that this time is taken. Offer these available times: {free_slots_str}. Ask for a new time."
                                            }
                                            await dg_agent.send(json.dumps(interrupt_message))
                                            
                                            # 3. Clear the time from state so we don't try to book it later
                                            conversation_state["appointment_time"] = None
                                            print("--> State time cleared. Agent notified.")
                                        else:
                                            print(f"DEBUG: Early check passed. Slot available: {is_available_early}")
                                    else:
                                        print(f"DEBUG: Early check skipped. Missing date or time here. Date: {current_date}, Time: {current_time}")
                                
                                # Check for hidden JSON payloads (Keep this just in case)
                                try:
                                    payload = json.loads(content)
                                    if payload.get("type") == "ready_to_book":
                                        print("[EVENT] Ready to book signal received.")
                                        print("Name: ", conversation_state["first_name"], conversation_state["last_name"])
                                        print("Date: ", conversation_state["appointment_date"])
                                        print("Time: ", conversation_state["appointment_time"])
                                        print("Reason: ", conversation_state["reason"])
                                        print(f"DEBUG: All conversation state values present: {conversation_state}")
                                        if all(conversation_state.values()):
                                            print(f"DEBUG: Entering final booking check. State: {conversation_state}")
                                            # --- CHECK AVAILABILITY (Final Gate) ---
                                            appt_date = conversation_state["appointment_date"]
                                            appt_time = conversation_state["appointment_time"]
                                            
                                            is_available = check_availability(appt_date, appt_time)

                                            if is_available:
                                                print(f"DEBUG: Final availability check passed ({is_available}). Proceeding.")
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
                                                print(f"DEBUG: Final availability check failed ({is_available}).")
                                                print("--> SLOT UNAVAILABLE (Final Check). Reporting back...")
                                                # This fallback should rarely be hit now with early check
                                                # But if it is, use the same injection strategy
                                                
                                                free_slots = get_available_slots_tool(appt_date)
                                                free_slots_str = ", ".join(free_slots) if free_slots else "No slots available"
                                                
                                                interrupt_message = {
                                                    "type": "ConversationText",
                                                    "role": "user",
                                                    "content": f"[SYSTEM ALERT]: The requested time is UNAVAILABLE. Tell the user it's taken and offer: {free_slots_str}."
                                                }
                                                await dg_agent.send(json.dumps(interrupt_message))
                                                conversation_state["appointment_time"] = None
                                                print(f"DEBUG: Cleared appointment_time in state due to unavailability (Final Check). New State: {conversation_state}")

                                        else:
                                            print(f"DEBUG: Missing fields in final check. State: {conversation_state}")
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