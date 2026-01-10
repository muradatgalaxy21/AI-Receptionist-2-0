# Run this command in terminal to create database at your end
# NEVER push DB on git
# python services/database.py

import sqlite3
from datetime import datetime

DB_NAME = "appointments.db"

def init_db():
    """
    Creates the database table if it doesn't exist.
    """
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS appointments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_name TEXT,
            phone_number TEXT,
            appointment_time DATETIME,
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

def book_appointment(name, phone, time_str):
    """
    Saves the appointment to the database.
    """
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    try:
        cursor.execute('''
            INSERT INTO appointments (customer_name, phone_number, appointment_time)
            VALUES (?, ?, ?)
        ''', (name, phone, time_str))
        conn.commit()
        print(f"Booking saved for {name} at {time_str}")
        return True
    except Exception as e:
        print(f"Error booking: {e}")
        return False
    finally:
        conn.close()

# Initialize the DB immediately when this file is imported
init_db()