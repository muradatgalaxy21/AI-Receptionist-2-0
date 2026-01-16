# Run this command in terminal to create database at your end
# NEVER push DB on git
# python services/database.py

import sqlite3
from datetime import datetime
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_NAME = os.path.join(BASE_DIR, "appointments.db")

# print(DB_NAME)
# print(BASE_DIR)


def init_db():
    """
    Creates the database table if it doesn't exist.
    """
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
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

def is_slot_available(time_str):
    """
    Checks if a specific time slot is free.
    Format: 'YYYY-MM-DD HH:MM'
    """
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    # Check if any appointment exists at this exact time
    cursor.execute('''
        SELECT count(*) FROM appointments 
        WHERE appointment_time = ? AND status = 'confirmed'
    ''', (time_str,))
    
    count = cursor.fetchone()[0]
    conn.close()
    
    # If count is 0, the slot is free
    return count == 0

def book_appointment(first_name, last_name, appointment_date, appointment_time, reason):
    print("book_appointment() CALLED")
    """
    Saves the appointment to the database.
    """
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    try:
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

# import os
# print("DB PATH:", os.path.abspath(DB_NAME))

# Initialize the DB immediately when this file is imported
# init_db()
    