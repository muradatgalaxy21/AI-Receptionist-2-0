# services/conversation_logger.py
# Handles logging of agent conversations to timestamped text files.
# Used by both the Twilio voice path and the text test path.

from pathlib import Path
from datetime import datetime
from typing import Optional


# 1. Base directory for all conversation log files
LOGS_DIR: Path = Path(__file__).resolve().parent.parent / "tests" / "conversation_logs"


class ConversationLogger:
    """
    Writes timestamped conversation transcripts to disk.
    Each session gets its own file named session_YYYYMMDD_HHMMSS.txt.
    """

    def __init__(self, session_label: Optional[str] = None) -> None:
        """
        Initialize a new conversation logger.
        1. Creates the logs directory if it does not already exist.
        2. Generates a unique filename based on current timestamp.
        3. Opens the file and writes a header line.
        """
        try:
            LOGS_DIR.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            print(f"ConversationLogger: Could not create log directory: {e}")

        # 2. Build the filename with optional label prefix
        timestamp: str = datetime.now().strftime("%Y%m%d_%H%M%S")
        prefix: str = f"{session_label}_" if session_label else "session_"
        self._file_path: Path = LOGS_DIR / f"{prefix}{timestamp}.txt"

        # 3. Write the header
        try:
            with open(self._file_path, "w", encoding="utf-8") as f:
                f.write(f"=== Conversation Log - {datetime.now().isoformat()} ===\n")
                if session_label:
                    f.write(f"Session Type: {session_label}\n")
                f.write("\n")
        except OSError as e:
            print(f"ConversationLogger: Could not write header: {e}")

    @property
    def file_path(self) -> Path:
        """Return the path to the log file."""
        return self._file_path

    def log(self, role: str, content: str) -> None:
        """
        Append a single message to the log file.
        1. Formats the entry with a timestamp and role label.
        2. Writes it to the file in append mode.
        """
        timestamp: str = datetime.now().strftime("%H:%M:%S")
        entry: str = f"[{timestamp}] {role.upper()}: {content}\n"
        try:
            with open(self._file_path, "a", encoding="utf-8") as f:
                f.write(entry)
        except OSError as e:
            print(f"ConversationLogger: Could not write log entry: {e}")

    def log_event(self, event: str) -> None:
        """
        Append a system event (not a user/agent message) to the log.
        1. Adds a bracketed event line with timestamp.
        """
        timestamp: str = datetime.now().strftime("%H:%M:%S")
        entry: str = f"[{timestamp}] --- {event} ---\n"
        try:
            with open(self._file_path, "a", encoding="utf-8") as f:
                f.write(entry)
        except OSError as e:
            print(f"ConversationLogger: Could not write event: {e}")

    def close(self) -> None:
        """
        Write a closing footer to the log file.
        """
        try:
            with open(self._file_path, "a", encoding="utf-8") as f:
                f.write(f"\n=== Session Ended - {datetime.now().isoformat()} ===\n")
        except OSError as e:
            print(f"ConversationLogger: Could not write footer: {e}")
