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

def book_appointment_tool(name, phone, time_str):
    """
    Saves to both Local DB and Google Calendar.
    """
    # 1. Save locally
    db_success = database.book_appointment(name, phone, time_str)
    
    # 2. Sync to Cloud
    cal_success = calendar.add_google_event(name, time_str)
    
    return db_success and cal_success