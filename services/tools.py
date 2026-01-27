from services import database
from datetime import datetime
from dateutil import parser
from dateutil.relativedelta import relativedelta

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
        # Handle specific relative terms manually for precision
        if "today" in d:
            return now.strftime("%Y-%m-%d")
        elif "tomorrow" in d:
            return (now + relativedelta(days=1)).strftime("%Y-%m-%d")
        elif "day after" in d:
            return (now + relativedelta(days=2)).strftime("%Y-%m-%d")
        
        # Use the powerful library for everything else ("next Tuesday", "Jan 21")
        # fuzzy=True allows it to ignore extra words like "on", "the"
        parsed_date = parser.parse(d, fuzzy=True, default=now)
        
        # If the parsed date is in the past (e.g. user says "Monday" but it's Tuesday),
        # assume they mean NEXT week.
        if parsed_date.date() < now.date():
            parsed_date += relativedelta(weeks=1)
            
        return parsed_date.strftime("%Y-%m-%d")
    except Exception as e:
        print(f"Date Parse Error: {e}")
        return date_str  # Return original string if we can't parse it

def check_availability(date: str, time: str = None):
    print(f"Checking availability for {date} (Time: {time})...")
    real_date = parse_date(date)
    print(f"   -> Converted '{date}' to '{real_date}'")

    if not time or "all" in time.lower() or "any" in time.lower():
        return "The available times are 12:00 PM, 2:00 PM, and 4:00 PM."

    available = database.is_slot_available(real_date, time)
    return available

def get_available_slots_tool(date: str):
    real_date = parse_date(date)
    return database.get_available_slots(real_date)



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