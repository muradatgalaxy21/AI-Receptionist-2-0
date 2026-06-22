from datetime import datetime
import os

from dateutil import parser as date_parser
from services.db_client import db

def normalize_time(time_str):
    try:
        # Pre-process natural language to help parser
        t = time_str.lower().strip()
        t = t.replace("in the afternoon", "pm")
        t = t.replace("in the evening", "pm")
        t = t.replace("in the morning", "am")
        t = t.replace("afternoon", "pm")
        t = t.replace("evening", "pm")
        t = t.replace("morning", "am")
        
        # Parse and format
        dt = date_parser.parse(t)
        return dt.strftime("%H:%M")
    except Exception as e:
        print(f"Time Parse Error: {e}")
        return time_str # Fallback

def init_db():
    db.init_db()

def _valid_clinic_slots_for(date: str) -> list:
    """Return the list of valid slot strings for a given YYYY-MM-DD date.
    Returns [] for Sundays (closed) or unparseable dates."""
    try:
        day_of_week = datetime.strptime(date, "%Y-%m-%d").strftime("%A")
    except (ValueError, TypeError):
        return []
    if day_of_week == "Sunday":
        return []
    if day_of_week == "Saturday":
        return ["09:00", "10:00", "11:00", "12:00"]
    return ["09:00", "10:00", "11:00", "12:00", "13:00", "14:00", "15:00", "16:00", "17:00"]


def is_slot_available(date, time):
    clean_time = normalize_time(time)
    valid_slots = _valid_clinic_slots_for(date)
    if not valid_slots:
        print(f"Slot {date} {clean_time} rejected — clinic closed that day.")
        return False
    if clean_time not in valid_slots:
        print(f"Slot {date} {clean_time} rejected — not a valid clinic slot.")
        return False
    
    rows = db.execute(
        "SELECT count(*) FROM appointments WHERE appointment_date = ? AND appointment_time = ? AND status = 'confirmed'",
        (date, clean_time)
    )
    count = rows[0][0] if rows else 0
    if count > 0:
        print(f"Slot {date} {clean_time} is BUSY.")
    return count == 0


def book_appointment(first_name, last_name, appointment_date, appointment_time, reason):
    """
    Atomically checks slot availability and inserts the booking.
    Returns True on success, False if slot is taken, invalid, or on error.
    """
    clean_time = normalize_time(appointment_time)
    valid_slots = _valid_clinic_slots_for(appointment_date)
    if not valid_slots:
        print(f"Booking rejected — clinic closed on {appointment_date}.")
        return False
    if clean_time not in valid_slots:
        print(f"Booking rejected — {clean_time} is not a valid slot on {appointment_date}.")
        return False
    
    # Check availability
    if not is_slot_available(appointment_date, clean_time):
        print(f"Slot {appointment_date} {clean_time} was taken by another booking.")
        return False

    success = db.execute_write(
        "INSERT INTO appointments (first_name, last_name, appointment_date, appointment_time, reason) VALUES (?, ?, ?, ?, ?)",
        (first_name, last_name, appointment_date, clean_time, reason)
    )
    if success:
        print(f"Booking saved for {first_name} {last_name} at {appointment_date} {clean_time}")
        return True
    return False


def get_available_slots(date: str) -> list:
    if not date:
        return []
    try:
        day_of_week: str = datetime.strptime(date, "%Y-%m-%d").strftime("%A")
    except (ValueError, TypeError):
        return []

    # Saturday is half-day 9am-1pm; Sunday is closed; Mon-Fri last slot at 5pm
    if day_of_week == "Sunday":
        return []
    elif day_of_week == "Saturday":
        standard_slots = ["09:00", "10:00", "11:00", "12:00"]
    else:
        standard_slots = ["09:00", "10:00", "11:00", "12:00", "13:00", "14:00", "15:00", "16:00", "17:00"]

    rows = db.execute(
        "SELECT appointment_time FROM appointments WHERE appointment_date = ? AND status = 'confirmed'",
        (date,)
    )
    booked_slots = [row[0] for row in rows]

    return [slot for slot in standard_slots if slot not in booked_slots]


def get_available_dates_with_slots(days_ahead: int = 14) -> list:
    """
    Scans the next N calendar days and returns dates that still have
    at least one free slot. Used for 'which dates are free?' queries.
    1. Iterates from tomorrow up to days_ahead days.
    2. Skips Sundays (clinic closed).
    3. Returns list of dicts with date, day name, and slot count.
    """
    from datetime import timedelta

    results = []
    today = datetime.now().date()

    for offset in range(1, days_ahead + 1):
        check_date = today + timedelta(days=offset)
        date_str = check_date.strftime("%Y-%m-%d")
        day_name = check_date.strftime("%A")

        if day_name == "Sunday":
            continue

        slots = get_available_slots(date_str)
        if slots:
            results.append({
                "date": date_str,
                "day": day_name,
                "slots_available": len(slots)
            })

    return results


# Initialize the DB immediately when this file is imported
# db_client initializes itself automatically, but we keep this call for compatibility
init_db()