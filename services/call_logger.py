# services/call_logger.py
"""
Utility module for logging call details to the unified database.
"""

from typing import Any
from services.db_client import db

def append_call_log(
    timestamp: str,
    caller_id: str,
    to_number: str,
    patient_name: str,
    call_duration: float,
    intent: str,
    summary: str,
    transcript: str,
    status: str,
    estimated_value: float,
    recording_url: str,
) -> None:
    """Append a single call record to the unified database 'calls' table."""
    query = """
        INSERT INTO calls (
            timestamp, caller_id, to_number, patient_name, call_duration, 
            intent, summary, transcript, status, estimated_value, recording_url
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """
    success = db.execute_write(query, (
        timestamp,
        caller_id,
        to_number,
        patient_name,
        call_duration,
        intent,
        summary,
        transcript,
        status,
        estimated_value,
        recording_url
    ))
    if success:
        print(f"call_logger: Saved call log with transcript to database for caller {caller_id}")
    else:
        print(f"call_logger: Failed to save call log to database")
