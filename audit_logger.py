import csv
import os
from datetime import datetime
import threading
import json


class AuditLogger:
    def __init__(self, filename="audit_trail.csv"):
        self.filepath = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".sandbox", filename)
        self.lock = threading.Lock()
        self._initialize_file()
        # Add a placeholder for the socketio object
        self.socketio = None

    def register_socketio(self, sio):
        """Allows the main app to register the Socket.IO instance."""
        self.socketio = sio

    def _initialize_file(self):
        """Creates the CSV file and writes the header if it doesn't exist."""
        with self.lock:
            file_exists = os.path.exists(self.filepath)
            os.makedirs(os.path.dirname(self.filepath), exist_ok=True)
            with open(self.filepath, "a", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                if not file_exists or os.path.getsize(self.filepath) == 0:
                    header = [
                        "Timestamp",
                        "Event",
                        "SessionID",
                        "SessionName",
                        "LoopID",
                        "Source",
                        "Destination",
                        "Observer",
                        "Details",
                    ]
                    writer.writerow(header)

    def log_event(
        self,
        event,
        session_id=None,
        session_name=None,
        loop_id=None,
        source=None,
        destination=None,
        observers=None,
        details=None,
        control_flow=None,
    ):
        """
        Logs a new event to the CSV file and broadcasts it over Socket.IO.
        """
        timestamp = datetime.now().isoformat()

        details_str = json.dumps(details) if details is not None else ""
        observer_str = ", ".join(observers) if isinstance(observers, list) else (observers or "N/A")

        def serialize(value):
            if value is None:
                return ""
            if isinstance(value, (dict, list)):
                return json.dumps(value)
            return str(value)

        log_data_for_csv = [
            timestamp,
            serialize(event),
            serialize(session_id or "N/A"),
            serialize(session_name or "N/A"),
            serialize(loop_id or "N/A"),
            serialize(source or "N/A"),
            serialize(destination or "N/A"),
            serialize(observer_str),
            serialize(details_str),
        ]

        with self.lock:
            # Write to CSV file
            with open(self.filepath, "a", newline="", encoding="utf-8") as f:
                writer = csv.writer(f, quoting=csv.QUOTE_ALL)
                writer.writerow(log_data_for_csv)

            # NEW: Broadcast the event over Socket.IO if available
            if self.socketio:
                log_data_for_broadcast = {
                    "event": event,
                    "source": source,
                    "destination": destination,
                    "session_id": session_id,
                    "loop_id": loop_id,
                    "details": details,
                }
                # Use a separate thread to avoid blocking
                self.socketio.start_background_task(self.socketio.emit, "new_audit_event", log_data_for_broadcast)


# Create a single, global instance to be used by the entire application
audit_log = AuditLogger()
