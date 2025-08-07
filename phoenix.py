"""
Main application bootstrap file.

This script initializes the Flask application and the SocketIO server, connects
to the persistent Haven service, and registers the web routes and SocketIO
event handlers. It is responsible for starting the server and bringing all
components of the application online.
"""
import time
import logging
from flask import Flask, send_from_directory
from flask_socketio import SocketIO
from flask_cors import CORS
from multiprocessing.managers import BaseManager
import debugpy
from typing import Optional

from config import DEBUG_MODE, SERVER_PORT, HAVEN_ADDRESS, HAVEN_AUTH_KEY
import events
from tracer import trace

# --- CONFIGURATION ---
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
app = Flask(__name__)
CORS(app)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="eventlet")

@trace
def connect_to_haven() -> Optional[BaseManager]:
    """
    Establishes a connection to the Haven service with a retry loop.

    This function is critical for the application's startup, ensuring a robust
    connection to the stateful backend process that manages the AI models.

    Returns:
        The Haven proxy object if connection is successful, otherwise None.
    """
    class HavenManager(BaseManager):
        pass

    HavenManager.register("get_haven")
    manager = HavenManager(address=HAVEN_ADDRESS, authkey=HAVEN_AUTH_KEY)

    # Retry loop provides robustness against timing issues during startup.
    for i in range(5):
        try:
            logging.info("Attempting to connect to Haven...")
            manager.connect()
            proxy = manager.get_haven()
            logging.info("Successfully connected to Haven and got proxy object.")
            return proxy
        except Exception as e:
            logging.warning(f"Haven connection failed. Retrying in {i + 1} second(s)... Error: {e}")
            time.sleep(i + 1)

    logging.critical("FATAL: Could not connect to Haven. The application cannot function without it.")
    return None

# --- GLOBAL INITIALIZATION ---
haven_proxy = connect_to_haven()
# Register all event handlers from the events module.
events.register_events(socketio, haven_proxy)


# --- SERVER ROUTES ---
@app.route("/")
@trace
def serve_index():
    """Serves the main chat interface."""
    return send_from_directory(".", "index.html")

@app.route("/<path:filename>")
@trace
def serve_static_files(filename: str):
    """Serves static files like CSS and JS from the root directory."""
    return send_from_directory(".", filename)

@app.route("/audit_visualizer")
@trace
def serve_audit_visualizer():
    """Serves the audit log visualization tool."""
    return send_from_directory(".", "audit_visualizer.html")

@app.route("/database_viewer")
@trace
def serve_database_viewer():
    """Serves the ChromaDB inspection tool."""
    return send_from_directory(".", "database_viewer.html")

@app.route("/docs")
@trace
def serve_docs():
    """Serves the documentation viewer."""
    return send_from_directory(".", "documentation_viewer.html")

@app.route("/documentation.md")
@trace
def serve_markdown():
    """Serves the raw markdown documentation file."""
    return send_from_directory(".", "documentation.md")

@app.route("/workshop")
@trace
def serve_workshop():
    """Serves the workshop/testing interface."""
    return send_from_directory(".", "workshop.html")


# --- MAIN EXECUTION ---
if __name__ == "__main__":
    if not haven_proxy:
        app.logger.critical("Server startup failed: Haven proxy could not be initialized.")
    else:
        if DEBUG_MODE:
            debugpy.listen(("0.0.0.0", 5678))
            app.logger.info("Debugpy server listening. Waiting for debugger to attach...")
            debugpy.wait_for_client()
            app.logger.info("Debugger attached.")

        app.logger.info(f"Starting Unified Agent Server on http://127.0.0.1:{SERVER_PORT}")
        socketio.run(app, port=SERVER_PORT)
