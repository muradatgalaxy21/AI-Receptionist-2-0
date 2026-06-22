# services/log_capture.py
"""
Intercepts sys.stdout and logging handlers to record the latest uvicorn
and application logs in memory, providing a live terminal-like output for the dashboard.
"""

import sys
import collections
import logging
import re
from typing import List

class LogCapture:
    def __init__(self, limit: int = 150) -> None:
        self.logs = collections.deque(maxlen=limit)
        self.original_stdout = sys.stdout
        sys.stdout = self

        # Custom logging handler to redirect standard Python logs (Uvicorn uses this)
        class CustomHandler(logging.Handler):
            def __init__(self, log_capture: 'LogCapture') -> None:
                super().__init__()
                self.log_capture = log_capture

            def emit(self, record: logging.LogRecord) -> None:
                try:
                    msg = self.format(record)
                    self.log_capture.append(msg)
                except Exception:
                    self.handleError(record)

        self.handler = CustomHandler(self)
        self.handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s', datefmt='%H:%M:%S'))
        
        # Attach to logging root and uvicorn loggers
        logging.getLogger().addHandler(self.handler)
        logging.getLogger("uvicorn").addHandler(self.handler)
        logging.getLogger("uvicorn.access").addHandler(self.handler)
        logging.getLogger("uvicorn.error").addHandler(self.handler)

    def write(self, message: str) -> None:
        # Pass to standard stdout stream so logs appear on Render console as normal
        self.original_stdout.write(message)
        
        # Store formatted log message in memory deque
        msg = message.strip()
        if msg:
            self.append(msg)

    def flush(self) -> None:
        self.original_stdout.flush()

    def append(self, msg: str) -> None:
        # Strip ANSI escape terminal colors to keep the web dashboard terminal clean
        ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
        clean_msg = ansi_escape.sub('', msg)
        self.logs.append(clean_msg)

    def get_logs(self) -> List[str]:
        return list(self.logs)

# Initialize singleton instance immediately
log_capturer = LogCapture()
