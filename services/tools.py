# The Tool Manager

from services import database, calendar

def check_availability_tool(time_str):
    """
    Combines SQLite and Google Calendar checks.
    Deepgram will call this function.
    """
    # 1. Check Local DB
    if not database.is_slot_available(time_str):
        return False
    
    # 2. Check Google Calendar
    if not calendar.check_google_calendar(time_str):
        return False
        
    return True

def book_appointment(first_name, last_name, reason, date, time):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    try:
        cursor.execute('''
            INSERT INTO appointments 
            (first_name, last_name, reason, appointment_date, appointment_time)
            VALUES (?, ?, ?, ?, ?)
        ''', (first_name, last_name, reason, date, time))
        conn.commit()
        print("Appointment booked successfully")
        return True
    except Exception as e:
        print(f"DB Error: {e}")
        return False
    finally:
        conn.close()
