# services/agent_logic.py
# Shared logic for processing Deepgram agent responses for the Grand Horizon
# Hotel reservation flow. Both the Twilio voice path (routers/brain.py) and the
# text-test path (routers/text_test.py) run through here so recap extraction and
# the booking state machine stay identical across channels.

import re
import json
from typing import Dict, Optional, Any

from services.tools import parse_date, price_reservation, _load_room_types
from services.booking_id import generate_booking_id
from services.webhook_dispatcher import dispatch_booking_created

# Fields the agent must gather before a reservation can be created.
REQUIRED_BOOKING_FIELDS = [
    "first_name", "last_name", "phone_number", "room_type",
    "check_in_date", "check_out_date", "number_of_guests",
]


# ---------------------------------------------------------------------------
# No-op hooks kept for callers that still import them.
# The dental build injected real-time hourly slot availability here. A hotel
# books whole nights by room type, not hourly slots, so there is nothing to
# inject — these return False and let the message flow through untouched.
# ---------------------------------------------------------------------------
async def handle_user_slot_query(user_text: str, conversation_state: Dict[str, Any], dg_agent: Any) -> bool:
    return False


async def handle_date_selection_in_booking(user_text: str, conversation_state: Dict[str, Any], dg_agent: Any) -> bool:
    return False


# ---------------------------------------------------------------------------
# Farewell detection
# ---------------------------------------------------------------------------
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


# ---------------------------------------------------------------------------
# Recap field extraction (best-effort parity with the voice recap)
# ---------------------------------------------------------------------------
_RECAP_PATTERNS = {
    "first_name":       r"First Name:\s*(.*?)(?:$|\n|\.|,)",
    "last_name":        r"Last Name:\s*(.*?)(?:$|\n|\.|,)",
    "phone_number":     r"Phone(?: Number)?:\s*(.*?)(?:$|\n|\.|,)",
    "room_type":        r"Room(?: Type)?:\s*(.*?)(?:$|\n|\.|,)",
    "check_in_date":    r"Check[- ]?in(?: Date)?:\s*(.*?)(?:$|\n|\.|,)",
    "check_out_date":   r"Check[- ]?out(?: Date)?:\s*(.*?)(?:$|\n|\.|,)",
    "number_of_guests": r"(?:Number of )?Guests:\s*(.*?)(?:$|\n|\.|,)",
    "special_requests": r"Special Requests:\s*(.*?)(?:$|\n|\.|,)",
}


def extract_recap_fields(content: str, conversation_state: Dict[str, Any]) -> Dict[str, Any]:
    """If the agent spelled out a labelled recap, pull the fields into state."""
    if "First Name:" not in content or "Last Name:" not in content:
        return conversation_state

    print("--> DETECTED RECAP! Extracting reservation fields from text...")
    for key, pattern in _RECAP_PATTERNS.items():
        m = re.search(pattern, content, re.IGNORECASE)
        if m and m.group(1).strip():
            conversation_state[key] = m.group(1).strip()
    print(f"--> STATE UPDATED FROM RECAP: {conversation_state}")
    return conversation_state


# ---------------------------------------------------------------------------
# Booking state machine
# ---------------------------------------------------------------------------
def _coerce_guests(value: Any) -> Optional[int]:
    """Pull an integer guest count out of '2', '2 guests', 'two', etc."""
    if value is None:
        return None
    if isinstance(value, int):
        return value
    digits = re.search(r"\d+", str(value))
    if digits:
        return int(digits.group(0))
    words = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6}
    return words.get(str(value).strip().lower())


def finalize_booking(conversation_state: Dict[str, Any], call_sid: Optional[str] = None) -> Dict[str, Any]:
    """Validate the gathered fields, price the stay, mint a Booking ID, fire the
    booking.created webhook, and record the result in conversation_state.

    Returns a result dict:
      {"ok": True,  "booking_id", "message", "nights", "total_cost", ...}
      {"ok": False, "error": "<what to tell the guest>"}
    Idempotent: a second call after a confirmed booking just replays the result.
    """
    if conversation_state.get("booking_confirmed"):
        return {
            "ok": True,
            "already": True,
            "booking_id": conversation_state.get("booking_id"),
            "message": (
                f"That reservation is already confirmed under Booking ID "
                f"{conversation_state.get('booking_id')}."
            ),
        }

    missing = [f for f in REQUIRED_BOOKING_FIELDS if not conversation_state.get(f)]
    if missing:
        return {"ok": False, "error": f"Still missing: {', '.join(missing)}."}

    guests = _coerce_guests(conversation_state.get("number_of_guests"))
    if not guests or guests < 1:
        return {"ok": False, "error": "The number of guests is unclear. Please ask again."}

    priced = price_reservation(
        conversation_state["room_type"],
        conversation_state["check_in_date"],
        conversation_state["check_out_date"],
    )
    if "error" in priced:
        return {"ok": False, "error": priced["error"]}

    room = _load_room_types().get(priced["room_type"], {})
    max_occ = room.get("max_occupancy")
    if max_occ and guests > max_occ:
        return {
            "ok": False,
            "error": (
                f"The {priced['room_type']} holds up to {max_occ} guests. "
                f"Suggest a larger room type for {guests} guests."
            ),
        }

    special = (conversation_state.get("special_requests") or "none").strip()
    guest_name = f"{conversation_state['first_name']} {conversation_state['last_name']}".strip()
    booking_id = generate_booking_id()

    data = {
        "booking_id": booking_id,
        "guest_name": guest_name,
        "phone_number": conversation_state["phone_number"],
        "room_type": priced["room_type"],
        "check_in_date": priced["check_in_date"],
        "check_out_date": priced["check_out_date"],
        "number_of_guests": guests,
        "nights": priced["nights"],
        "total_cost": priced["total_cost"],
        "special_requests": special,
    }

    dispatch_booking_created(data, call_sid)

    # Optional Google Calendar mirror (self-disabling; never blocks the booking).
    try:
        from services.calender import add_reservation_to_calendar
        add_reservation_to_calendar(data)
    except Exception as e:
        print(f"[CALENDAR] sync skipped: {e}")

    conversation_state.update({
        "booking_confirmed": True,
        "booking_id": booking_id,
        "guest_name": guest_name,
        "room_type": priced["room_type"],
        "check_in_date": priced["check_in_date"],
        "check_out_date": priced["check_out_date"],
        "number_of_guests": guests,
        "nights": priced["nights"],
        "total_cost": priced["total_cost"],
        "special_requests": special,
        "_booking_just_confirmed": True,
    })

    print(f"RESERVATION CONFIRMED: {booking_id} | {guest_name} | {priced['room_type']} "
          f"| {priced['check_in_date']} -> {priced['check_out_date']} | "
          f"{priced['nights']} nights | ${priced['total_cost']}")

    message = (
        f"The reservation is confirmed. Booking ID {booking_id}. "
        f"{priced['nights']} night{'s' if priced['nights'] != 1 else ''} in the "
        f"{priced['room_type']} at {priced['nightly_rate']:.0f} dollars per night, "
        f"total {priced['total_cost']:.2f} dollars. A confirmation text is on its way to "
        f"{conversation_state['phone_number']}. Tell the guest, read the Booking ID "
        f"clearly, remind them check-in is at 3 PM, then ask if there is anything else. "
        f"Do NOT say goodbye yet."
    )
    return {
        "ok": True,
        "booking_id": booking_id,
        "message": message,
        "nights": priced["nights"],
        "nightly_rate": priced["nightly_rate"],
        "total_cost": priced["total_cost"],
        "room_type": priced["room_type"],
    }


# Maps book_room function arguments / ready_to_book payload keys to state keys.
_PAYLOAD_KEY_MAP = {
    "first_name": "first_name",
    "last_name": "last_name",
    "phone_number": "phone_number",
    "phone": "phone_number",
    "room_type": "room_type",
    "check_in_date": "check_in_date",
    "check_in": "check_in_date",
    "check_out_date": "check_out_date",
    "check_out": "check_out_date",
    "number_of_guests": "number_of_guests",
    "guests": "number_of_guests",
    "special_requests": "special_requests",
}


def _merge_payload_into_state(payload: Dict[str, Any], conversation_state: Dict[str, Any]) -> None:
    for src, dest in _PAYLOAD_KEY_MAP.items():
        if payload.get(src) not in (None, ""):
            conversation_state[dest] = payload[src]


async def handle_booking_function_call(
    fn_input: Dict[str, Any],
    conversation_state: Dict[str, Any],
    dg_agent: Any,
    call_sid: Optional[str] = None,
) -> str:
    """Handle a `book_room` FunctionCallRequest. Returns the text to send back
    as the FunctionCallResponse output (Deepgram speaks from it)."""
    _merge_payload_into_state(fn_input or {}, conversation_state)
    result = finalize_booking(conversation_state, call_sid)
    if result["ok"]:
        return result["message"]
    return (
        f"The reservation could not be completed yet: {result['error']} "
        f"Ask the guest for the missing or corrected detail, then call book_room again."
    )


async def try_book_from_json_payload(
    content: str,
    conversation_state: Dict[str, Any],
    dg_agent: Any,
    call_sid: Optional[str] = None,
) -> Dict[str, Any]:
    """Fallback path: the agent emitted a hidden {"type": "ready_to_book", ...}
    JSON object instead of calling the function. Book from it the same way."""
    try:
        payload = json.loads(content)
    except (json.JSONDecodeError, ValueError):
        return conversation_state
    if not isinstance(payload, dict) or payload.get("type") != "ready_to_book":
        return conversation_state

    if conversation_state.get("booking_confirmed"):
        print("[EVENT] ready_to_book ignored — reservation already confirmed this session.")
        return conversation_state

    print("[EVENT] ready_to_book signal received.")
    _merge_payload_into_state(payload, conversation_state)
    result = finalize_booking(conversation_state, call_sid)

    if result["ok"]:
        try:
            await dg_agent.send(json.dumps({
                "type": "InjectAgentMessage",
                "message": result["message"],
            }))
        except Exception as e:
            print(f"Error sending confirmation: {e}")
    else:
        try:
            await dg_agent.send(json.dumps({
                "type": "InjectUserMessage",
                "content": (
                    f"The booking is not ready: {result['error']} "
                    f"Ask the guest for the missing detail."
                ),
            }))
        except Exception as e:
            print(f"Error sending booking-incomplete notice: {e}")
    return conversation_state


async def process_agent_text_response(
    content: str,
    conversation_state: Dict[str, Any],
    dg_agent: Any,
    call_sid: Optional[str] = None,
) -> Dict[str, Any]:
    """Entry point for a ConversationText message from the agent.
    1. Suppress + act on a hidden ready_to_book JSON payload.
    2. Detect farewell -> mark session for closure.
    3. Extract a labelled recap if present.
    """
    # Pure JSON payload
    try:
        pure = json.loads(content)
        if isinstance(pure, dict) and pure.get("type") == "ready_to_book":
            conversation_state["last_message_is_payload"] = True
            return await try_book_from_json_payload(content, conversation_state, dg_agent, call_sid)
    except (json.JSONDecodeError, ValueError):
        pass

    # Mixed message: JSON object plus trailing farewell text
    json_match = re.search(r'\{[^{}]*"type"\s*:\s*"ready_to_book"[^{}]*\}', content, re.DOTALL)
    if json_match:
        conversation_state["last_message_is_payload"] = True
        await try_book_from_json_payload(json_match.group(0), conversation_state, dg_agent, call_sid)
        remaining = content.replace(json_match.group(0), "").strip()
        if remaining and is_farewell(remaining):
            print("---> FAREWELL DETECTED (mixed payload). Marking session for closure.")
            conversation_state["session_should_end"] = True
        return conversation_state

    conversation_state["last_message_is_payload"] = False
    print(f"Sarah: {content}")

    # Right after a booking, Sarah's confirmation line may contain "have a great
    # day" — don't treat that as a farewell. Re-arm on the next turn.
    if conversation_state.get("_booking_just_confirmed"):
        conversation_state["_booking_just_confirmed"] = False
        return extract_recap_fields(content, conversation_state)

    if is_farewell(content):
        print("---> FAREWELL DETECTED. Marking session for closure.")
        conversation_state["session_should_end"] = True

    return extract_recap_fields(content, conversation_state)


if __name__ == "__main__":
    import asyncio

    class _FakeAgent:
        def __init__(self): self.sent = []
        async def send(self, m): self.sent.append(m)

    async def _demo():
        state = {
            "first_name": "Jane", "last_name": "Doe", "phone_number": "+15551234567",
            "room_type": "deluxe king", "check_in_date": "2026-09-10",
            "check_out_date": "2026-09-12", "number_of_guests": "2 guests",
            "special_requests": "high floor",
        }
        res = finalize_booking(state)
        assert res["ok"] and res["nights"] == 2 and res["total_cost"] == 398.0, res
        assert re.fullmatch(r"HTL-\d{4}[A-Z]", res["booking_id"]), res
        assert state["booking_confirmed"] and state["room_type"] == "Deluxe King"
        # Idempotent
        assert finalize_booking(state).get("already") is True

        # Missing field
        bad = finalize_booking({"first_name": "A"})
        assert not bad["ok"] and "missing" in bad["error"].lower(), bad

        # Over occupancy
        over = finalize_booking({
            "first_name": "B", "last_name": "C", "phone_number": "1", "room_type": "Standard Queen",
            "check_in_date": "2026-09-10", "check_out_date": "2026-09-11", "number_of_guests": 5,
        })
        assert not over["ok"] and "holds up to" in over["error"], over

        # Function-call path
        agent = _FakeAgent()
        s2 = {}
        out = await handle_booking_function_call({
            "first_name": "Sam", "last_name": "Lee", "phone_number": "+15550001111",
            "room_type": "Penthouse", "check_in_date": "2026-12-01",
            "check_out_date": "2026-12-04", "number_of_guests": 3,
        }, s2, agent)
        assert "Booking ID" in out and s2["booking_confirmed"], out
        print("OK - agent_logic:", res["booking_id"], "|", out[:60], "...")

    asyncio.run(_demo())
