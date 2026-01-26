import sqlite3
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_NAME = os.path.join(BASE_DIR, "appointments.db")

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

def book_appointment_db(first_name, last_name, reason, date, time):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    try:
        # Fixed: Now uses the correct column names matching init_db
        cursor.execute('''
            INSERT INTO appointments (first_name, last_name, reason, appointment_date, appointment_time)
            VALUES (?, ?, ?, ?, ?)
        ''', (first_name, last_name, reason, date, time))
        conn.commit()
        print(f"Booking saved for {first_name} {last_name} on {date} at {time}")
        return True
    except Exception as e:
        print(f"Error booking: {e}")
        return False
    finally:
        conn.close()

# Initialize immediately
init_db()