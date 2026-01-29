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
    print("book_appointment() CALLED")
    clean_time = normalize_time(appointment_time)
    
    """
    Saves the appointment to the database.
    """
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


def get_available_slots(date):
    """
    Returns a list of available times for a given date.
    Standard slots are now in 24-hour format for consistency.
    """
    # 10am to 8pm in 24h format
    standard_slots = ["10:00", "11:00", "12:00", "13:00", "14:00", "15:00", "16:00", "17:00", "18:00", "19:00", "20:00"]
    
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT appointment_time FROM appointments 
        WHERE appointment_date = ? AND status = 'confirmed'
    ''', (date,))
    booked_slots = [row[0] for row in cursor.fetchall()]
    conn.close()
    
    # Normalize booked slots to compare easily (stripping logic if needed, but assuming exact match for now)
    available = [slot for slot in standard_slots if slot not in booked_slots]
    return available

# Initialize the DB immediately when this file is imported
init_db()
    