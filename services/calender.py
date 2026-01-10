# services/calendar.py
import os
# We will install google-auth libraries later

def check_google_calendar(time_str):
    """
    Day 2 Task: Check Google Calendar for conflicts.
    For now, we return True (Available) so we can test SQLite first.
    """
    print(f"[MOCK] Checking Google Calendar for {time_str}...")
    return True

def add_google_event(name, time_str):
    """
    Day 2 Task: Add event to Google Calendar.
    """
    print(f"[MOCK] Adding to Google Calendar: {name} at {time_str}")
    return True