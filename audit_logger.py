# audit_logger.py

import csv
import os
from datetime import datetime
import threading

class AuditLogger:
    def __init__(self, filename="audit_trail.csv"):
        # Place the audit trail in the sandbox to keep the root directory clean
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
                    header = ["Timestamp", "Event", "SessionID", "SessionName", "Source", "Details"]
                    writer.writerow(header)

    def log_event(self, event, session_id=None, session_name=None, source=None, details=None):
        """Logs a new event to the CSV file."""
        timestamp = datetime.now().isoformat()
        
        # Sanitize details to prevent issues with CSV formatting
        if isinstance(details, dict) or isinstance(details, list):
            import json
            details_str = json.dumps(details)
        else:
            details_str = str(details) if details is not None else ""

        with self.lock:
            with open(self.filepath, 'a', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow([
                    timestamp,
                    event,
                    session_id or "N/A",
                    session_name or "N/A",
                    source or "N/A",
                    details_str
                ])

# Create a single, global instance to be used by the entire application
audit_log = AuditLogger()
