from flask import Flask, render_template, send_from_directory, request, jsonify
from flask_socketio import SocketIO
from flask_cors import CORS
import os
import logging
import json
from datetime import datetime
from orchestrator import execute_reasoning_loop, confirmation_events
from tool_agent import execute_tool_command, get_safe_path
from memory_manager import MemoryManager
from multiprocessing.managers import BaseManager
from audit_logger import audit_log
import inspect_db as db_inspector
import debugpy
import time

# --- Function to load the system prompt from a file ---
def load_system_prompt():
    try:
        prompt_path = os.path.join(os.path.dirname(__file__), 'public_data', 'system_prompt.txt')
        with open(prompt_path, 'r') as f:
            return f.read()
    except FileNotFoundError:
        return "You are a helpful assistant but were unable to locate or open system_prompt.txt, and thus do not have access to your core directives."

# --- Function to load the model definition from a file ---
def load_model_definition():
    try:
        model_definition_path = os.path.join(os.path.dirname(__file__), 'public_data', 'model_definition.txt')
        with open(model_definition_path, 'r') as f:
            return f.read().strip()
    except FileNotFoundError:
        return 'gemini-1.5-pro-001'

# --- CONFIGURATION ---
app = Flask(__name__)
CORS(app)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='eventlet')

# --- NEW: Register socketio with the audit logger ---
audit_log.register_socketio(socketio)

# --- Setup Logging ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s', handlers=[logging.FileHandler("agent.log"), logging.StreamHandler()])

# --- REMOVED: GEMINI SETUP IS NOW IN HAVEN ---
# The 'model' object is no longer created or used directly in app.py

# --- NEW: Connect to the Haven to get the remote Haven object ---
class HavenManager(BaseManager):
    pass

HavenManager.register('get_haven')
manager = HavenManager(address=('localhost', 50000), authkey=b'phoenixhaven')
haven_proxy = None

# Add a retry loop for robustness
for i in range(5):
    try:
        manager.connect()
        haven_proxy = manager.get_haven()
        logging.info("Successfully connected to Haven and got proxy object.")
        break
    except Exception as e:
        logging.warning(f"Haven connection refused or failed. Retrying in {i+1} second(s)... Error: {e}")
        time.sleep(i+1)

if not haven_proxy:
    logging.critical("FATAL: Could not connect to Haven after multiple retries. The application cannot function without it.")
    # In a real scenario, we might exit or serve an error page.
    # For now, we'll log a critical error and continue, but most things will fail.

# This dictionary holds session-specific data for currently connected clients.
# It does NOT hold the expensive chat objects anymore.
# The structure will be: { session_id: { "memory": MemoryManager_instance, "name": "session_name" } }
chat_sessions = {}
client_session_map = {}

# --- SERVER ROUTES & EVENTS ---
@app.route('/')
def serve_index():
    return send_from_directory('.', 'index.html')

# --- (Other routes remain the same) ---

@app.route('/audit_visualizer')
def serve_audit_visualizer():
    return send_from_directory('.', 'audit_visualizer.html')

@app.route('/database_viewer')
def serve_database_viewer():
    return send_from_directory('.', 'database_viewer.html')

@app.route('/docs')
def serve_docs():
    return send_from_directory('.', 'documentation_viewer.html')

@app.route('/documentation.md')
def serve_markdown():
    return send_from_directory('.', 'documentation.md')

@app.route('/workshop')
def serve_workshop():
    return send_from_directory('.', 'workshop.html')

@app.route('/visualizer')
def serve_visualizer():
    return send_from_directory('.', 'code_visualizer.html')

@app.route('/get_diagram')
def get_diagram_file():
    try:
        diagram_path = get_safe_path('code_flow.md')
        if os.path.exists(diagram_path):
            return send_from_directory(os.path.dirname(diagram_path), os.path.basename(diagram_path))
        else:
            return "Diagram not found. Please generate it first.", 404
    except Exception as e:
        return str(e), 500

# --- SOCKETIO EVENTS ---

@socketio.on('connect')
def handle_connect():
    session_id = request.sid
    timestamp = datetime.now().strftime("%d%b%Y_%I%M%S%p").upper()
    new_session_name = f"New_Session_{timestamp}"

    audit_log.log_event("Client Connected", session_id=session_id, session_name=new_session_name, source="Application", destination="Client")
    app.logger.info(f"Client connected: {session_id}")

    if haven_proxy:
        try:
            # Create a local MemoryManager for this new, unsaved session.
            memory = MemoryManager(session_name=new_session_name)
            
            # The 'chat' object is no longer stored here. We only store the name and memory manager.
            chat_sessions[session_id] = {
                "memory": memory,
                "name": new_session_name
            }
            app.logger.info(f"Local session stub created for {session_id} with name {new_session_name}")
            
            socketio.emit('session_name_update', {'name': new_session_name}, to=session_id)
            
        except Exception as e:
            app.logger.exception(f"Could not create local session stub for {session_id}.")
            socketio.emit('log_message', {'type': 'error', 'data': 'Failed to initialize session.'}, to=session_id)
    else:
        socketio.emit('log_message', {'type': 'error', 'data': 'Haven service not available.'}, to=request.sid)

@socketio.on('disconnect')
def handle_disconnect():
    session_id = request.sid
    session_data = chat_sessions.get(session_id)

    if session_data:
        session_name = session_data.get('name')
        app.logger.info(f"Client disconnected: {session_id}, Session: {session_name}")
        audit_log.log_event("Client Disconnected", session_id=session_id, session_name=session_name, source="Client", destination="Server")
    else:
        app.logger.info(f"Client disconnected: {session_id} (No session data found).)")
        audit_log.log_event("Client Disconnected", session_id=session_id, session_name="N/A", source="Client", destination="Server")

    chat_sessions.pop(session_id, None)
    confirmation_events.pop(session_id, None)

@socketio.on('start_task')
def handle_start_task(data):
    session_id = request.sid
    session_data = chat_sessions.get(session_id)
    if not session_data:
        socketio.emit('log_message', {'type': 'error', 'data': 'No active session. Please refresh.'}, to=request.sid)
        return
        
    session_name = session_data.get('name')
    audit_log.log_event("Socket.IO Event Received: start_task", session_id=session_id, session_name=session_name, source="Client", destination="Server", details=data)
    prompt = data.get('prompt')
    
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    timestamped_prompt = f"[{timestamp}] {prompt}"
    
    socketio.emit('display_user_prompt', {'prompt': timestamped_prompt}, to=session_id)

    if prompt:
        # Pass the haven_proxy to the reasoning loop
        socketio.start_background_task(execute_reasoning_loop, socketio, session_data, timestamped_prompt, session_id, chat_sessions, haven_proxy)
    
# --- (Other socketio handlers like log_audit_event, request_session_list, etc. remain the same for now) ---
# --- but will need to be updated to use the haven_proxy where appropriate ---

@socketio.on('log_audit_event')
def handle_audit_event(data):
    audit_log.log_event(
        event=data.get('event'),
        session_id=request.sid,
        session_name=chat_sessions.get(request.sid, {}).get('name'),
        loop_id=None,
        source=data.get('source'),
        destination=data.get('destination'),
        details=data.get('details'),
        control_flow=data.get('control_flow')
    )

@socketio.on('request_session_list')
def handle_session_list_request():
    session_id = request.sid
    session_name = chat_sessions.get(session_id, {}).get('name')
    audit_log.log_event("Socket.IO Event Received: request_session_list", session_id=session_id, session_name=session_name, source="Client", destination="Server")
    # Pass the haven_proxy to the tool command executor
    tool_result = execute_tool_command({'action': 'list_sessions'}, socketio, session_id, chat_sessions, haven_proxy)
    audit_log.log_event("Socket.IO Emit: session_list_update", session_id=session_id, session_name=session_name, source="Server", destination="Client", details=tool_result)
    socketio.emit('session_list_update', tool_result, to=request.sid)


@socketio.on('request_session_name')
def handle_session_name_request():
    session_id = request.sid
    session_data = chat_sessions.get(session_id)
    if session_data:
        name = session_data.get('name')
        socketio.emit('session_name_update', {'name': name}, to=request.sid)

@socketio.on('user_confirmation')
def handle_user_confirmation(data):
    session_id = request.sid
    event = confirmation_events.get(session_id)
    if event:
        event.send(data.get('response'))

if __name__ == '__main__':
    if not haven_proxy:
        app.logger.critical("Server startup failed: Haven proxy could not be initialized.")
    else:
        app.logger.info("Starting Unified Agent Server on http://127.0.0.1:5001")
        audit_log.log_event("SocketIO Server Started", source="System", destination="System")
        socketio.run(app, port=5001)