# services/call_logger.py
"""
Utility module for logging call details to a CSV file.
All writes are performed safely with exception handling and
the header row is created automatically if the file does not exist.
"""

import csv
from pathlib import Path
from typing import Any

# CSV file location – placed in the project root for easy access
CALL_LOG_PATH: Path = Path(__file__).resolve().parents[1] / "call_logs.csv"


def _ensure_file_exists() -> None:
    """Create the CSV file with a header if it does not already exist."""
    if not CALL_LOG_PATH.exists():
        try:
            CALL_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
            with CALL_LOG_PATH.open("w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow([
                    "timestamp",
                    "caller_id",
                    "patient_name",
                    "call_duration",
                    "intent",
                    "summary",
                    "status",
                    "estimated_value",
                    "recording_url",
                ])
        except OSError as e:
            print(f"call_logger: Failed to create log file: {e}")


def append_call_log(
    timestamp: str,
    caller_id: str,
    patient_name: str,
    call_duration: float,
    intent: str,
    summary: str,
    status: str,
    estimated_value: float,
    recording_url: str,
) -> None:
    """Append a single call record to ``call_logs.csv``.

    All arguments are expected to be serialisable as strings or numbers.
    The function ensures the CSV exists and handles any I/O errors
    gracefully, printing a human‑readable message on failure.
    """
    _ensure_file_exists()
    try:
        with CALL_LOG_PATH.open("a", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([
                timestamp,
                caller_id,
                patient_name,
                f"{call_duration:.2f}",
                intent,
                summary,
                status,
                f"{estimated_value:.2f}",
                recording_url,
            ])
    except OSError as e:
        print(f"call_logger: Failed to write call log entry: {e}")
