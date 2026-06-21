# services/agent_logic.py
# Shared logic for processing Deepgram agent responses.
# Extracted from routers/brain.py so both Twilio and text-test paths
# use the exact same recap extraction, availability checking, and booking logic.

import re
import json
from datetime import datetime
from typing import Dict, Optional, Any

from services.database import book_appointment, get_available_dates_with_slots
from services.tools import check_availability, parse_date, get_available_slots_tool

# Keywords indicating user is explicitly asking about available slots/times.
SLOT_QUERY_KEYWORDS: list = [
    "which slot", "which time", "what time", "free slot", "available slot",
    "open slot", "free time", "available time", "any slot", "any time",
    "what slots", "what times", "which times", "slots available", "times available",
    "slot free", "open time", "is there any slot", "what are the slots",
    "when can i come", "when can i book", "which hours",
]

# Keywords indicating user is asking about which DATES have availability.
DATE_AVAILABILITY_KEYWORDS: list = [
    "which date", "what date", "which day", "what day", "any date", "any day",
    "which dates", "what dates", "which days", "what days",
    "when are you free", "when is available", "earliest available",
    "soonest available", "next available",
]


def _to_12h(slot: str) -> str:
    """Convert a 24h HH:MM slot string to a readable 12h AM/PM format."""
    try:
        dt = datetime.strptime(slot, "%H:%M")
        return dt.strftime("%I:%M %p").lstrip("0")
    except Exception:
        return slot


def _ordinal(n: int) -> str:
    """Return a number with the correct English ordinal suffix (1st, 2nd, 3rd, 4th…)."""
    if 11 <= n % 100 <= 13:
        return f"{n}th"
    return f"{n}" + {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")


def _extract_date_from_user_text(text: str) -> Optional[str]:
    """
    Try to extract a date reference from the user's raw message.
    1. Looks for explicit date patterns (dd-mm-yyyy, dd/mm/yyyy, 'May 21').
    2. Falls back to relative phrases ('today', 'tomorrow', 'next thursday').
    3. Returns a parsed YYYY-MM-DD string, or None if nothing found.
    """
    text_lower: str = text.lower().strip()

    # Explicit date patterns: 21-05-2026 / 21/05/2026 / May 21 / 21st May etc.
    explicit_pattern = re.search(
        r"(\d{1,2}[-/]\d{1,2}[-/]\d{2,4}|\d{4}[-/]\d{1,2}[-/]\d{1,2}"
        r"|(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]* \d{1,2}"
        r"|\d{1,2}(?:st|nd|rd|th)? (?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*)",
        text_lower
    )
    if explicit_pattern:
        return parse_date(explicit_pattern.group(0))

    # Relative day keywords -- order matters: check multi-word phrases first
    relative_keywords = [
        "next monday", "next tuesday", "next wednesday", "next thursday",
        "next friday", "next saturday", "next sunday",
        "this monday", "this tuesday", "this wednesday", "this thursday",
        "this friday", "this saturday", "this sunday",
        "day after tomorrow",
        "today", "tomorrow",
        "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday",
    ]
    for kw in relative_keywords:
        if kw in text_lower:
            return parse_date(kw)

    return None


async def handle_date_selection_in_booking(
    user_text: str,
    conversation_state: Dict[str, Any],
    dg_agent: Any
) -> bool:
    """
    Proactively inject real available slots whenever the user mentions a date
    AND we are already in a booking flow (i.e. we have the patient's name).
    This prevents Sarah from offering appointment slots when the user mentions
    any date in passing (e.g. "I had a filling last Monday").
    """
    # Only inject slot data if we're in an active booking flow (have name, not yet confirmed)
    if not conversation_state.get("first_name"):
        return False
    if conversation_state.get("booking_confirmed"):
        return False

    # Try to extract a date from what the user just said
    target_date: Optional[str] = _extract_date_from_user_text(user_text)
    if not target_date:
        return False

    # Query the DB for real free slots
    available_slots: list = get_available_slots_tool(target_date)
    readable: list = [_to_12h(s) for s in available_slots]

    print(f"[BOOKING DATE] Date: {target_date} | Free slots: {readable}")

    if readable:
        if len(readable) == 1:
            slots_str = readable[0]
        elif len(readable) == 2:
            slots_str = f"{readable[0]} and {readable[1]}"
        else:
            slots_str = ", ".join(readable[:-1]) + f", and {readable[-1]}"
        inject_content: str = (
            f"The patient mentioned {target_date}. The available slots for that day are {slots_str}. "
            f"Tell the patient these options and ask which time they prefer."
        )
    else:
        inject_content: str = (
            f"The patient mentioned {target_date}. Unfortunately all slots for that day are fully booked. "
            f"Let them know and ask if they would like to try a different date."
        )

    try:
        await dg_agent.send(json.dumps({"type": "InjectUserMessage", "content": inject_content}))
    except Exception as e:
        print(f"[BOOKING DATE] Injection error: {e}")

    return True


async def handle_user_slot_query(
    user_text: str,
    conversation_state: Dict[str, Any],
    dg_agent: Any
) -> bool:
    """
    Handle explicit user queries about available slots or dates.
    Covers two cases:
      A) 'Which slots are free on Thursday?' -- date-specific slot lookup.
      B) 'Which dates are available?' -- multi-date scan.

    1. Detects query type from keywords.
    2. Queries the DB appropriately.
    3. Injects a SYSTEM message with real data for the AI to relay.

    Returns True if query was handled, False otherwise.
    """
    text_lower: str = user_text.lower()

    # Case B: User asking which dates have availability (multi-date scan)
    is_date_query: bool = any(kw in text_lower for kw in DATE_AVAILABILITY_KEYWORDS)
    if is_date_query:
        print("[SLOT QUERY] Multi-date availability query detected.")
        available_dates: list = get_available_dates_with_slots(days_ahead=14)

        if available_dates:
            summaries = [
                f"{d['day']} the {_ordinal(int(d['date'].split('-')[2]))}"
                for d in available_dates[:5]
            ]
            if len(summaries) == 1:
                dates_str = summaries[0]
            elif len(summaries) == 2:
                dates_str = f"{summaries[0]} and {summaries[1]}"
            else:
                dates_str = ", ".join(summaries[:-1]) + f", and {summaries[-1]}"
            inject_content: str = (
                f"We have availability on the following dates in the next two weeks: {dates_str}. "
                f"Let the patient know these options and ask which date works best for them."
            )
        else:
            inject_content: str = (
                "Unfortunately all appointment slots for the next two weeks are fully booked. "
                "Let the patient know and suggest they call back in a few days."
            )

        try:
            await dg_agent.send(json.dumps({"type": "InjectUserMessage", "content": inject_content}))
        except Exception as e:
            print(f"[SLOT QUERY] Multi-date injection error: {e}")
        return True

    # Case A: User asking about slots on a specific date
    is_slot_query: bool = any(kw in text_lower for kw in SLOT_QUERY_KEYWORDS)
    if not is_slot_query:
        return False

    target_date: Optional[str] = _extract_date_from_user_text(user_text)

    if not target_date:
        # Date not mentioned -- ask for it
        inject_content = (
            "The patient is asking about available times but has not mentioned a specific date. "
            "Please ask them which date they are thinking of."
        )
        try:
            await dg_agent.send(json.dumps({"type": "InjectUserMessage", "content": inject_content}))
        except Exception as e:
            print(f"[SLOT QUERY] No-date injection error: {e}")
        return True

    available_slots = get_available_slots_tool(target_date)
    readable = [_to_12h(s) for s in available_slots]
    print(f"[SLOT QUERY] Date: {target_date} | Available: {readable}")

    if readable:
        if len(readable) == 1:
            slots_str = readable[0]
        elif len(readable) == 2:
            slots_str = f"{readable[0]} and {readable[1]}"
        else:
            slots_str = ", ".join(readable[:-1]) + f", and {readable[-1]}"
        inject_content = (
            f"For {target_date} the available appointment times are {slots_str}. "
            f"Share these options with the patient and ask which time suits them."
        )
    else:
        inject_content = (
            f"Unfortunately {target_date} is fully booked. "
            f"Let the patient know and ask if they would like to try a different date."
        )

    try:
        await dg_agent.send(json.dumps({"type": "InjectUserMessage", "content": inject_content}))
    except Exception as e:
        print(f"[SLOT QUERY] Injection error: {e}")

    return True


# Farewell phrases — only ones that are unambiguous end-of-call signals.
# Removed "take care" / "see you soon" / "have a wonderful" because they
# can appear naturally mid-conversation ("We'll take care of that for you",
# "See you soon at your appointment", "Hope you have a wonderful smile").
FAREWELL_PHRASES: list = [
    "goodbye",
    "good bye",
    "have a great day",
    "thank you for calling",
    "thank you, goodbye",
    "thank you. goodbye",
]


def is_farewell(content: str) -> bool:
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
                f"The time {current_time} on {current_date} has just been taken by another patient. "
                f"Apologise to the user and let them know that slot is no longer available. "
                f"The remaining open times for that day are {free_slots_str}. Ask them to choose one."
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

        real_date: str = parse_date(appt_date)
        if not real_date:
            print(f"--> Date parse failed for '{appt_date}'. Cannot book.")
            return conversation_state

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
                    f"Bright Smile Dental Care. Have a great day. Goodbye!"
                )
            }
            try:
                await dg_agent.send(json.dumps(confirmation_message))
            except Exception as e:
                print(f"Error sending confirmation: {e}")

            conversation_state["booking_confirmed"] = True
    else:
        print(f"DEBUG: Final availability check failed ({is_available}).")
        print("--> SLOT UNAVAILABLE (Final Check). Reporting back...")

        free_slots = get_available_slots_tool(appt_date)
        free_slots_str = ", ".join(free_slots) if free_slots else "No slots available"

        interrupt_message = {
            "type": "InjectUserMessage",
            "content": (
                f"That appointment slot is no longer available. "
                f"Apologise to the patient and offer these alternative times instead: {free_slots_str}."
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
    # Step 1: Handle pure JSON payload OR mixed JSON+text (e.g. JSON + "Goodbye!")
    # Extract JSON block from content using regex so booking works even when
    # the agent appends farewell text after the JSON object.
    json_match = re.search(r'\{[^{}]*"type"\s*:\s*"ready_to_book"[^{}]*\}', content, re.DOTALL)
    try:
        pure_payload = json.loads(content)
        # Only treat as a booking payload if it's specifically a ready_to_book dict.
        # Any other valid JSON dict (e.g. debug output) must not be suppressed.
        if isinstance(pure_payload, dict) and pure_payload.get("type") == "ready_to_book":
            conversation_state["last_message_is_payload"] = True
            conversation_state = await try_book_from_json_payload(
                content, conversation_state, dg_agent
            )
            return conversation_state
    except (json.JSONDecodeError, ValueError):
        pass

    if json_match:
        # Mixed message — extract JSON and process booking, then handle farewell
        json_str = json_match.group(0)
        conversation_state["last_message_is_payload"] = True
        conversation_state = await try_book_from_json_payload(
            json_str, conversation_state, dg_agent
        )
        remaining = content.replace(json_str, "").strip()
        if remaining and is_farewell(remaining):
            print("---> FAREWELL DETECTED (mixed payload). Marking session for closure.")
            conversation_state["session_should_end"] = True
        return conversation_state

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
