# services/agent_logic.py
# Shared logic for processing Deepgram agent responses.
# Extracted from routers/brain.py so both Twilio and text-test paths
# use the exact same recap extraction, availability checking, and booking logic.

import re
import json
from typing import Dict, Optional, Any

from services.database import book_appointment
from services.tools import check_availability, parse_date, get_available_slots_tool

# Farewell phrases that signal the agent intends to end the call.
# When any of these appear in the agent's text the session should close.
FAREWELL_PHRASES: list = [
    "goodbye",
    "good bye",
    "have a great day",
    "take care",
    "thank you for calling",
    "thank you, goodbye",
    "thank you. goodbye",
    "see you soon",
    "have a wonderful",
]


def is_farewell(content: str) -> bool:
    """
    Return True if the agent's message contains a recognisable farewell phrase.
    1. Normalises the content to lowercase.
    2. Checks against the FAREWELL_PHRASES list.

    Args:
        content: The agent's spoken text.

    Returns:
        True if a farewell phrase is present, False otherwise.
    """
    lowered: str = content.lower()
    return any(phrase in lowered for phrase in FAREWELL_PHRASES)


def extract_recap_fields(content: str, conversation_state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Detect a recap message and extract structured fields via regex.
    1. Checks if the content contains the recap markers (First Name + Last Name).
    2. Uses regex patterns to pull each field value after its label.
    3. Updates the conversation_state dict in-place and returns it.

    Args:
        content: The agent's spoken text.
        conversation_state: Current conversation state dict to update.

    Returns:
        The updated conversation_state dict.
    """
    if "First Name:" not in content or "Last Name:" not in content:
        return conversation_state

    print("--> DETECTED RECAP! Extracting data from text...")
    print(f"DEBUG: Checking regex matches on content: {content}")

    # 2. Regex patterns for each field
    first_name_match = re.search(r"First Name:\s*(.*?)(?:$|\n|\.|,)", content)
    last_name_match = re.search(r"Last Name:\s*(.*?)(?:$|\n|\.|,)", content)
    date_match = re.search(r"(?:Appointment )?Date:\s*(.*?)(?:$|\n|\.|,)", content)
    time_match = re.search(r"(?:Appointment )?Time:\s*(.*?)(?:$|\n|\.|,)", content)
    reason_match = re.search(r"Reason:\s*(.*?)(?:$|\n|\.|,)", content)

    print(f"DEBUG: Matches -> Name: {first_name_match}, Date: {date_match}, Time: {time_match}")

    # 3. Apply matched values to state
    if first_name_match:
        conversation_state["first_name"] = first_name_match.group(1).strip()
    if last_name_match:
        conversation_state["last_name"] = last_name_match.group(1).strip()
    if date_match:
        conversation_state["appointment_date"] = date_match.group(1).strip()
    if time_match:
        conversation_state["appointment_time"] = time_match.group(1).strip()
    if reason_match:
        conversation_state["reason"] = reason_match.group(1).strip()

    print(f"--> STATE UPDATED FROM TEXT: {conversation_state}")
    return conversation_state


async def check_early_availability(
    content: str,
    conversation_state: Dict[str, Any],
    dg_agent: Any
) -> Dict[str, Any]:
    """
    Check if a confirmed time slot is available BEFORE the full recap/booking flow.
    1. Detects the phrase "I will record the appointment time as" in agent speech.
    2. Extracts date and time from state and the utterance.
    3. If the slot is taken, injects a system alert to notify the agent.
    4. Clears the time from state so the user is asked for a new one.

    Args:
        content: The agent's spoken text.
        conversation_state: Current conversation state dict.
        dg_agent: The Deepgram WebSocket connection to inject messages into.

    Returns:
        The updated conversation_state dict.
    """
    if "I will record the appointment time as" not in content:
        return conversation_state

    current_date: Optional[str] = conversation_state.get("appointment_date")

    # Extract the time from this specific utterance for precision
    time_match_instant = re.search(
        r"I will record the appointment time as\s+(.*?)(?:$|\n|\.|,)", content
    )
    print(f"DEBUG: Instant Time Match: {time_match_instant}")

    current_time: Optional[str] = (
        time_match_instant.group(1).strip()
        if time_match_instant
        else conversation_state.get("appointment_time")
    )

    if not current_date or not current_time:
        print(
            f"DEBUG: Early check skipped. Missing date or time. "
            f"Date: {current_date}, Time: {current_time}"
        )
        return conversation_state

    print(
        f"--> EARLY CHECK DETECTED for {current_date} at {current_time} "
        f"(State: {conversation_state})"
    )
    is_available_early = check_availability(current_date, current_time)
    print(f"DEBUG: check_availability result: {is_available_early}")

    if not is_available_early:
        print(
            f"DEBUG: Entering Early Warning Block. "
            f"Current Date: {current_date}, Time: {current_time}"
        )
        print("--> EARLY WARNING: SLOT TAKEN. Interrupting Agent...")

        # 1. Get alternative time slots
        free_slots = get_available_slots_tool(current_date)
        free_slots_str = ", ".join(free_slots) if free_slots else "No slots available"

        # 2. Inject system message to force the agent to correct itself
        interrupt_message = {
            "type": "InjectUserMessage",
            "content": (
                f"[SYSTEM ALERT]: The time {current_time} on {current_date} is "
                f"UNAVAILABLE. You must STOP and inform the user that this time is "
                f"taken. Offer these available times: {free_slots_str}. Ask for a new time."
            )
        }
        try:
            await dg_agent.send(json.dumps(interrupt_message))
        except Exception as e:
            print(f"Error sending interrupt message: {e}")

        # 3. Clear the time from state
        conversation_state["appointment_time"] = None
        print("--> State time cleared. Agent notified.")
    else:
        print(f"DEBUG: Early check passed. Slot available: {is_available_early}")

    return conversation_state


async def try_book_from_json_payload(
    content: str,
    conversation_state: Dict[str, Any],
    dg_agent: Any
) -> Dict[str, Any]:
    """
    Check if the agent emitted a hidden JSON payload signaling readiness to book.
    1. Attempts to parse the content as JSON.
    2. If it contains type=ready_to_book, validates all required fields.
    3. Checks final availability and either books or sends an alert.

    Args:
        content: The agent's spoken text (may contain JSON).
        conversation_state: Current conversation state dict.
        dg_agent: The Deepgram WebSocket connection.

    Returns:
        The updated conversation_state dict.
    """
    try:
        payload = json.loads(content)
    except (json.JSONDecodeError, ValueError):
        # Not a JSON message -- plain text, skip
        return conversation_state

    # Guard: valid JSON values like integers ("12"), booleans, or lists
    # are not booking payloads. Only a dict can carry the expected fields.
    if not isinstance(payload, dict):
        return conversation_state

    if payload.get("type") != "ready_to_book":
        return conversation_state

    # Guard: if the appointment was already booked in this session, ignore
    # subsequent ready_to_book signals (e.g. triggered by the user's farewell).
    if conversation_state.get("booking_confirmed"):
        print("[EVENT] ready_to_book ignored -- appointment already confirmed this session.")
        return conversation_state

    print("[EVENT] Ready to book signal received.")

    # Extract fields directly from the payload if the agent embedded them.
    # This is the primary data source -- reliable even when the agent skips
    # a spoken recap and jumps straight to emitting the JSON signal.
    field_map: dict = {
        "first_name":        ("first_name",        payload.get("first_name")),
        "last_name":         ("last_name",         payload.get("last_name")),
        "appointment_date":  ("appointment_date",  payload.get("date")),
        "appointment_time":  ("appointment_time",  payload.get("time")),
        "reason":            ("reason",            payload.get("reason")),
    }
    for state_key, (_, value) in field_map.items():
        if value:
            conversation_state[state_key] = value

    print("Name: ", conversation_state["first_name"], conversation_state["last_name"])
    print("Date: ", conversation_state["appointment_date"])
    print("Time: ", conversation_state["appointment_time"])
    print("Reason: ", conversation_state["reason"])
    print(f"DEBUG: All conversation state values present: {conversation_state}")

    if not all(conversation_state.get(k) for k in ["first_name", "last_name", "appointment_date", "appointment_time", "reason"]):
        print(f"DEBUG: Missing fields in final check. State: {conversation_state}")
        print("--> Missing fields. Cannot book yet.")
        return conversation_state


    print(f"DEBUG: Entering final booking check. State: {conversation_state}")

    appt_date: str = conversation_state["appointment_date"]
    appt_time: str = conversation_state["appointment_time"]

    is_available = check_availability(appt_date, appt_time)

    if is_available:
        print(f"DEBUG: Final availability check passed ({is_available}). Proceeding.")
        print("--> All fields present & Slot Available. Booking now...")

        # Use parsed date for storage consistency
        real_date: str = parse_date(appt_date)

        success: bool = book_appointment(
            conversation_state["first_name"],
            conversation_state["last_name"],
            real_date,
            appt_time,
            conversation_state["reason"]
        )
        if success:
            print("APPOINTMENT BOOKED!")

            # Send a confirmation + farewell via InjectAgentMessage.
            # Ending with "Goodbye!" ensures the farewell detection in
            # process_agent_text_response will set session_should_end = True
            # causing the CLI and Twilio router to close the call cleanly.
            confirmation_message = {
                "type": "InjectAgentMessage",
                "message": (
                    f"Perfect! Your appointment has been confirmed for "
                    f"{real_date} at {appt_time}. Thank you for calling "
                    f"Doctor Farooq's Dental Clinic. Have a great day. Goodbye!"
                )
            }
            try:
                await dg_agent.send(json.dumps(confirmation_message))
            except Exception as e:
                print(f"Error sending confirmation: {e}")

            conversation_state["booking_confirmed"] = True
            conversation_state["waiting_for_final_response"] = True
    else:
        print(f"DEBUG: Final availability check failed ({is_available}).")
        print("--> SLOT UNAVAILABLE (Final Check). Reporting back...")

        free_slots = get_available_slots_tool(appt_date)
        free_slots_str = ", ".join(free_slots) if free_slots else "No slots available"

        interrupt_message = {
            "type": "InjectUserMessage",
            "content": (
                f"[SYSTEM ALERT]: The requested time is UNAVAILABLE. "
                f"Tell the user it's taken and offer: {free_slots_str}."
            )
        }
        try:
            await dg_agent.send(json.dumps(interrupt_message))
        except Exception as e:
            print(f"Error sending unavailability alert: {e}")

        conversation_state["appointment_time"] = None
        print(
            f"DEBUG: Cleared appointment_time in state due to unavailability "
            f"(Final Check). New State: {conversation_state}"
        )

    return conversation_state


async def process_agent_text_response(
    content: str,
    conversation_state: Dict[str, Any],
    dg_agent: Any
) -> Dict[str, Any]:
    """
    Main entry point for processing a ConversationText message from the agent.
    Chains together all processing steps in order:
    1. Suppress and handle hidden JSON payloads before any display.
    2. Detect farewell phrases and mark the session for closure.
    3. Extract recap fields if present.
    4. Check early availability if time confirmation detected.
    5. Try booking from hidden JSON payload.

    Args:
        content: The agent's spoken text content.
        conversation_state: Current conversation state dict.
        dg_agent: The Deepgram WebSocket connection.

    Returns:
        The updated conversation_state dict with a possible
        'session_should_end' key set to True.
    """
    # Step 1: If the content is a raw JSON payload (e.g. ready_to_book),
    # process it silently and mark it so callers can suppress display.
    try:
        payload = json.loads(content)
        if isinstance(payload, dict):
            # Mark the message as a hidden payload so the CLI/router can
            # skip printing it to avoid surfacing raw JSON to the user.
            conversation_state["last_message_is_payload"] = True
            conversation_state = await try_book_from_json_payload(
                content, conversation_state, dg_agent
            )
            return conversation_state
    except (json.JSONDecodeError, ValueError):
        pass

    # Reset the payload flag for normal text messages
    conversation_state["last_message_is_payload"] = False

    print(f"Sarah: {content}")

    # Step 2: Detect farewell -- mark session for clean shutdown
    if is_farewell(content):
        print("---> FAREWELL DETECTED. Marking session for closure.")
        conversation_state["session_should_end"] = True

    # Step 3: Extract recap fields from structured text
    conversation_state = extract_recap_fields(content, conversation_state)

    # Step 4: Early availability check on time confirmation
    conversation_state = await check_early_availability(
        content, conversation_state, dg_agent
    )

    # Step 5: Fallback -- also try JSON booking signal (handles edge cases)
    conversation_state = await try_book_from_json_payload(
        content, conversation_state, dg_agent
    )

    return conversation_state
