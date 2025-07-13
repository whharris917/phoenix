# audit_logger.py

import csv
import os
from datetime import datetime
import threading
import json # Import json at the top

class AuditLogger:
    def __init__(self, filename="audit_trail.csv"):
        self.filepath = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.sandbox', filename)
        self.lock = threading.Lock()
        self._initialize_file()

    def _initialize_file(self):
        """Creates the CSV file and writes the header if it doesn't exist."""
        with self.lock:
            file_exists = os.path.exists(self.filepath)
            os.makedirs(os.path.dirname(self.filepath), exist_ok=True)
            with open(self.filepath, 'a', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                if not file_exists or os.path.getsize(self.filepath) == 0:
                    header = ["Timestamp", "Event", "SessionID", "SessionName", "LoopID", "Source", "Destination", "Observer", "Details"]
                    writer.writerow(header)

    def log_event(self, event, session_id=None, session_name=None, loop_id=None, source=None, destination=None, observers=None, details=None):
        """
        Logs a new event to the CSV file.
        'observers' should be a list of roles that can see this event.
        """
        timestamp = datetime.now().isoformat()
        
        # --- FIX: ALWAYS use json.dumps to sanitize the details field ---
        # This properly escapes all special characters (quotes, newlines, commas)
        # ensuring the data is contained within a single CSV cell.
        details_str = json.dumps(details) if details is not None else ""
        
        observer_str = ", ".join(observers) if isinstance(observers, list) else (observers or "N/A")

        with self.lock:
            with open(self.filepath, 'a', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow([
                    timestamp,
                    event,
                    session_id or "N/A",
                    session_name or "N/A",
                    loop_id or "N/A",
                    source or "N/A",
                    destination or "N/A",
                    observer_str,
                    details_str
                ])

# Create a single, global instance to be used by the entire application
audit_log = AuditLogger()
