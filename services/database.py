import sqlite3
from datetime import datetime
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_NAME = os.path.join(BASE_DIR, "appointments.db")

# print(DB_NAME)
# print(BASE_DIR)


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
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    # Check if a slot is taken on a specific DATE and TIME
    cursor.execute('''
        SELECT count(*) FROM appointments 
        WHERE appointment_date = ? AND appointment_time = ? AND status = 'confirmed'
    ''', (date, time))
    count = cursor.fetchone()[0]
    conn.close()
    return count == 0

def book_appointment(first_name, last_name, appointment_date, appointment_time, reason):
    print("book_appointment() CALLED")
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
        ''', (first_name, last_name, appointment_date, appointment_time, reason))
        conn.commit()
        print(f"Booking saved for {first_name} {last_name} at {appointment_date} {appointment_time}")
        return True
    except Exception as e:
        print(f"Error booking: {e}")
        return False
    finally:
        conn.close()


def get_available_slots(date):
    """
    Returns a list of available times for a given date.
    Standard slots: 10:00 AM, 12:00 PM, 2:00 PM, 4:00 PM
    """
    standard_slots = ["10:00 AM", "11:00 AM", "12:00 PM", "01:00 PM", "02:00 PM", "03:00 PM", "04:00 PM", "05:00 PM", "06:00 PM", "07:00 PM", "08:00 PM"]
    
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
    