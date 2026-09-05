from services import database
from datetime import datetime
from dateutil import parser
from dateutil.relativedelta import relativedelta
import json
import os
import re

_DATA_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "data.json")

def parse_date(date_str: str):
    """
    Uses dateutil to smartly convert 'tomorrow', 'next friday', etc.
    """
    if not date_str:
        return None
    
    # Clean the string
    d = date_str.lower().strip()
    now = datetime.now()

    try:
        # ISO / year-first dates (YYYY-MM-DD or YYYY/MM/DD) are unambiguous —
        # take them verbatim. dateutil with dayfirst=True mis-reads "2026-09-10"
        # as day 09 / month 10, which the hotel booking flow (dates supplied in
        # YYYY-MM-DD) would hit on every reservation.
        iso = re.match(r"^(\d{4})[-/](\d{1,2})[-/](\d{1,2})$", d)
        if iso:
            try:
                return datetime(int(iso.group(1)), int(iso.group(2)), int(iso.group(3))).strftime("%Y-%m-%d")
            except ValueError:
                return None

        # Handle specific relative terms manually for precision
        if "today" in d:
            return now.strftime("%Y-%m-%d")
        elif "tomorrow" in d:
            return (now + relativedelta(days=1)).strftime("%Y-%m-%d")
        elif "day after" in d:
            return (now + relativedelta(days=2)).strftime("%Y-%m-%d")

        # Use the powerful library for everything else ("next Tuesday", "Jan 21")
        # fuzzy=True allows it to ignore extra words like "on", "the"
        # dayfirst=True enforces DMY format (e.g. 01/02 is Feb 1st, not Jan 2nd)
        parsed_date = parser.parse(d, fuzzy=True, dayfirst=True, default=now)
        
        # Check if year was explicitly mentioned (4 digits)
        # If user said "2026", we shouldn't shift the date even if it looks like past.
        # Use regex to find 4 digits, since split() + isdigit() fails on "01-02-2026"
        year_explicitly_mentioned = re.search(r"\d{4}", d) is not None

        # If the parsed date is in the past AND year wasn't specified, assume next week.
        if parsed_date.date() < now.date() and not year_explicitly_mentioned:
            parsed_date += relativedelta(weeks=1)
            
        return parsed_date.strftime("%Y-%m-%d")
    except Exception as e:
        print(f"Date Parse Error: {e}")
        return None

def check_availability(date: str, time: str) -> bool:
    real_date = parse_date(date)
    if not real_date:
        return False
    return database.is_slot_available(real_date, time)

def get_available_slots_tool(date: str):
    real_date = parse_date(date)
    if not real_date:
        return []
    return database.get_available_slots(real_date)



# ---------------------------------------------------------------------------
# Hotel stay duration & pricing
# ---------------------------------------------------------------------------

def _load_room_types() -> dict:
    """Read the room_types map from data/data.json. Returns {} on any error."""
    try:
        with open(_DATA_PATH, "r", encoding="utf-8") as f:
            return json.load(f).get("room_types", {})
    except Exception as e:
        print(f"[tools] Could not load room types: {e}")
        return {}


def match_room_type(room_type: str):
    """Resolve a spoken room name to the canonical key in data.json.

    Case-insensitive, and tolerant of extra words ('a deluxe king room').
    Returns the canonical name (e.g. 'Deluxe King') or None.
    """
    if not room_type:
        return None
    want = room_type.strip().lower()
    rooms = _load_room_types()
    for name in rooms:
        if name.lower() == want:
            return name
    for name in rooms:
        if name.lower() in want:
            return name
    return None


def get_nightly_rate(room_type: str):
    """Nightly rate (float) for a room type, or None if unknown."""
    canonical = match_room_type(room_type)
    if not canonical:
        return None
    rate = _load_room_types()[canonical].get("nightly_rate")
    return float(rate) if rate is not None else None


def calculate_nights(check_in: str, check_out: str) -> int:
    """Number of nights between two dates. Accepts YYYY-MM-DD or natural
    language ('next friday'). Returns 0 if unparseable or check-out is not
    after check-in."""
    ci, co = parse_date(check_in), parse_date(check_out)
    if not ci or not co:
        return 0
    nights = (datetime.strptime(co, "%Y-%m-%d") - datetime.strptime(ci, "%Y-%m-%d")).days
    return nights if nights > 0 else 0


def price_reservation(room_type: str, check_in: str, check_out: str) -> dict:
    """Compute stay duration and total cost for a reservation.

    Returns a dict with canonical room_type, check_in_date, check_out_date
    (both normalised to YYYY-MM-DD), nights, nightly_rate and total_cost.
    On bad input the dict carries an 'error' key instead.
    """
    canonical = match_room_type(room_type)
    if not canonical:
        return {"error": f"Unknown room type: {room_type!r}"}

    ci, co = parse_date(check_in), parse_date(check_out)
    if not ci or not co:
        return {"error": "Could not understand the check-in or check-out date."}

    nights = calculate_nights(ci, co)
    if nights <= 0:
        return {"error": "Check-out date must be after the check-in date."}

    rate = get_nightly_rate(canonical)
    return {
        "room_type": canonical,
        "check_in_date": ci,
        "check_out_date": co,
        "nights": nights,
        "nightly_rate": rate,
        "total_cost": round(rate * nights, 2),
    }


def book_appointment_tool(name: str, reason: str, date: str, time: str):
    print(f"Booking: {name} | {date} | {time}")
    real_date = parse_date(date)
    
    # Simple Name Split
    parts = name.strip().split(" ")
    first = parts[0]
    last = " ".join(parts[1:]) if len(parts) > 1 else "(No Last Name)"
    
    success = database.book_appointment(first, last, real_date, time, reason)
    
    if success:
        return f"Success! Booked for {first} on {real_date} at {time}."
    else:
        return "System Error: Database failed."


if __name__ == "__main__":
    # Self-check for the hotel pricing helper.
    assert calculate_nights("2026-09-10", "2026-09-12") == 2
    assert calculate_nights("2026-09-10", "2026-09-10") == 0
    assert calculate_nights("2026-09-12", "2026-09-10") == 0
    assert match_room_type("a deluxe king room") == "Deluxe King"
    assert match_room_type("penthouse") == "Penthouse"
    assert match_room_type("igloo") is None

    p = price_reservation("Deluxe King", "2026-09-10", "2026-09-12")
    assert p["nights"] == 2 and p["nightly_rate"] == 199.0 and p["total_cost"] == 398.0, p
    assert "error" in price_reservation("Deluxe King", "2026-09-12", "2026-09-10")
    print("OK - pricing helper:", p)
