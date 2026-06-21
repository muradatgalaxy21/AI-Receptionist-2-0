import sqlite3
from datetime import datetime
import os

from dateutil import parser as date_parser

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_NAME = os.path.join(BASE_DIR, "appointments.db")

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
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    # Correct Schema
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS appointments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            first_name TEXT NOT NULL,
            last_name TEXT NOT NULL,
            reason TEXT NOT NULL,
            appointment_date TEXT NOT NULL,
            appointment_time TEXT NOT NULL,
            status TEXT DEFAULT 'confirmed'
        )
    ''')
    conn.commit()
    conn.close()
    print("Database initialized.")

def is_slot_available(date, time):
    clean_time = normalize_time(time)
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    # Check if a slot is taken on a specific DATE and TIME
    cursor.execute('''
        SELECT count(*) FROM appointments 
        WHERE appointment_date = ? AND appointment_time = ? AND status = 'confirmed'
    ''', (date, clean_time))
    count = cursor.fetchone()[0]
    conn.close()
    if count > 0:
        print(f"Slot {date} {clean_time} is BUSY.")
    return count == 0

def book_appointment(first_name, last_name, appointment_date, appointment_time, reason):
    clean_time = normalize_time(appointment_time)
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    try:
        # Fixed: Now uses the correct column names matching init_db
        cursor.execute('''
            INSERT INTO appointments (first_name, last_name, appointment_date, appointment_time, reason)
            VALUES (?, ?, ?, ?, ?)
        ''', (first_name, last_name, appointment_date, clean_time, reason))
        conn.commit()
        print(f"Booking saved for {first_name} {last_name} at {appointment_date} {clean_time}")
        return True
    except Exception as e:
        print(f"Error booking: {e}")
        return False
    finally:
        conn.close()


def get_available_slots(date: str) -> list:
    """
    Returns a list of available time slots for a given date.
    1. Determines slot range based on day of week (Saturday is half-day).
    2. Queries the DB for already-booked slots on that date.
    3. Returns only the slots that are NOT booked.
    """
    try:
        day_of_week: str = datetime.strptime(date, "%Y-%m-%d").strftime("%A")
    except ValueError:
        day_of_week = "Monday"

    # Saturday is half-day 9am-1pm; Sunday is closed; Mon-Fri last slot at 5pm
    if day_of_week == "Sunday":
        return []
    elif day_of_week == "Saturday":
        standard_slots = ["09:00", "10:00", "11:00", "12:00"]
    else:
        standard_slots = ["09:00", "10:00", "11:00", "12:00", "13:00", "14:00", "15:00", "16:00", "17:00"]

    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT appointment_time FROM appointments WHERE appointment_date = ? AND status = 'confirmed'",
        (date,)
    )
    booked_slots = [row[0] for row in cursor.fetchall()]
    conn.close()

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
init_db()