from flask import Flask, render_template, send_from_directory, request, jsonify
from flask_socketio import SocketIO
from flask_cors import CORS
import google.generativeai as genai
import os
import logging
import json
import atexit
from datetime import datetime
from orchestrator import execute_reasoning_loop, confirmation_events
from tool_agent import execute_tool_command, get_safe_path
from memory_manager import MemoryManager
from audit_logger import audit_log
import inspect_db as db_inspector
import debugpy

# --- Function to load API key from a file ---
def load_api_key():
    try:
        key_path = os.path.join(os.path.dirname(__file__), 'private_data', 'Gemini_API_Key.txt')
        with open(key_path, 'r') as f:
            return f.read().strip()
    except FileNotFoundError:
        return None

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
            return f.read()
    except FileNotFoundError:
        return 'gemini-2.5-pro'

# --- CONFIGURATION ---
API_KEY = load_api_key()
SYSTEM_PROMPT = load_system_prompt()
MODEL_DEFINITION = load_model_definition()
API_STATS_FILE = os.path.join(os.path.dirname(__file__), 'api_usage.json')
app = Flask(__name__)
CORS(app)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='eventlet')

# --- NEW: Register socketio with the audit logger ---
audit_log.register_socketio(socketio)

# --- Setup Logging ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s', handlers=[logging.FileHandler("agent.log"), logging.StreamHandler()])

# --- GEMINI SETUP ---
model = None
if API_KEY:
    try:
        genai.configure(api_key=API_KEY)
        safety_settings = {
            'HARM_CATEGORY_HARASSMENT': 'BLOCK_NONE',
            'HARM_CATEGORY_HATE_SPEECH': 'BLOCK_NONE',
            'HARM_CATEGORY_SEXUALLY_EXPLICIT': 'BLOCK_NONE',
            'HARM_CATEGORY_DANGEROUS_CONTENT': 'BLOCK_NONE',
        }
        model = genai.GenerativeModel(
            model_name=MODEL_DEFINITION,
            system_instruction=SYSTEM_PROMPT,
            safety_settings=safety_settings
        )
        logging.info("Gemini API configured successfully.")
    except Exception as e:
        logging.critical(f"FATAL: Failed to configure Gemini API. Error: {e}")
else:
    logging.critical("FATAL: Gemini API key not loaded.")

# --- API Usage Tracking ---
def load_api_stats():
    try:
        with open(API_STATS_FILE, 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {'total_calls': 0, 'total_prompt_tokens': 0, 'total_completion_tokens': 0}

def save_api_stats():
    audit_log.log_event("Server Shutdown", source="System", destination="System", observers=["Orchestrator"])
    with open(API_STATS_FILE, 'w') as f:
        json.dump(api_stats, f, indent=4)
    logging.info("API usage statistics saved.")

api_stats = load_api_stats()
atexit.register(save_api_stats)

chat_sessions = {}

# --- SERVER ROUTES & EVENTS ---
@app.route('/')
def serve_index():
    return send_from_directory('.', 'index.html')

# --- NEW: Add route for the audit visualizer ---
@app.route('/audit_visualizer')
def serve_audit_visualizer():
    return send_from_directory('.', 'audit_visualizer.html')

# --- NEW: Add route for the database viewer ---
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

# The following functions handle emissions to the application from the client and orchestrator

@socketio.on('connect')
def handle_connect():
    session_id = request.sid
    timestamp = datetime.now().strftime("%d%b%Y_%I%M%S%p").upper()
    new_session_name = f"New_Session_{timestamp}"
    
    audit_log.log_event("Client Connected", session_id=session_id, session_name=new_session_name, source="Application", destination="Client", observers=["Application, Client"])
    app.logger.info(f"Client connected: {session_id}")
    if model:
        try:
            # --- MODIFIED: Initialize MemoryManager with the persistent session_name ---
            memory = MemoryManager(session_name=new_session_name)
            chat_sessions[session_id] = {
                "chat": model.start_chat(history=memory.get_full_history()),
                "memory": memory,
                "name": new_session_name
            }
            app.logger.info(f"Chat and MemoryManager session created for {session_id} with name {new_session_name}")
            
            audit_log.log_event("Socket.IO Emit: session_name_update", session_id=session_id, session_name=new_session_name, source="Application", destination="Client", observers=["User", "Orchestrator"], details={'name': new_session_name})
            socketio.emit('session_name_update', {'name': new_session_name}, to=session_id)

            # --- NEW: Send the (potentially loaded) history to the client ---
            full_history = memory.get_full_history()
            if full_history:
                audit_log.log_event("Socket.IO Emit: full_history_update", session_id=session_id, session_name=new_session_name, source="Application", destination="Client", observers=["User"], details=f"{len(full_history)} turns loaded")
                socketio.emit('load_chat_history', {'history': full_history}, to=session_id)

        except Exception as e:
            app.logger.exception(f"Could not create chat session for {session_id}.")
            socketio.emit('log_message', {'type': 'error', 'data': 'Failed to initialize AI session.'}, to=session_id)
    else:
        socketio.emit('log_message', {'type': 'error', 'data': 'AI model not available.'}, to=request.sid)


@socketio.on('disconnect')
def handle_disconnect():
    session_id = request.sid
    # Get the full session data before removing it.
    session_data = chat_sessions.get(session_id)

    if session_data:
        session_name = session_data.get('name')
        app.logger.info(f"Client disconnected: {session_id}, Session: {session_name}")
        audit_log.log_event("Client Disconnected", session_id=session_id, session_name=session_name, source="Client", destination="Server", observers=["Orchestrator"])

        # Check if the session was a default, unsaved session and clean it up.
        if session_name and session_name.startswith("New_Session_"):
            try:
                memory = session_data.get('memory')
                if memory:
                    app.logger.info(f"Auto-deleting unsaved session collection: '{session_name}'")
                    memory.clear()  # This deletes the ChromaDB collection.
                    audit_log.log_event(
                        "DB Collection Deleted",
                        session_id=session_id,
                        session_name=session_name,
                        source="System",
                        destination="Database",
                        observers=["Orchestrator"],
                        details=f"Unsaved session '{session_name}' automatically cleaned up on disconnect."
                    )
            except Exception as e:
                app.logger.error(f"Error during automatic cleanup of session '{session_name}': {e}")
    else:
        # Fallback for cases where session data might already be gone.
        app.logger.info(f"Client disconnected: {session_id} (No session data found).)")
        audit_log.log_event("Client Disconnected", session_id=session_id, session_name="N/A", source="Client", destination="Server", observers=["Orchestrator"])

    # Final cleanup of the application state.
    chat_sessions.pop(session_id, None)
    confirmation_events.pop(session_id, None)

@socketio.on('start_task')
def handle_start_task(data):
    session_id = request.sid
    session_name = chat_sessions.get(session_id, {}).get('name')
    audit_log.log_event("Socket.IO Event Received: start_task", session_id=session_id, session_name=session_name, source="Client", destination="Server", observers=["Orchestrator"], details=data)
    prompt = data.get('prompt')
    session_data = chat_sessions.get(session_id)
    if prompt and session_data:
        socketio.start_background_task(execute_reasoning_loop, socketio, session_data, prompt, session_id, chat_sessions, model, api_stats)
    elif not session_data:
        socketio.emit('log_message', {'type': 'error', 'data': 'No active AI session. Please refresh.'}, to=request.sid)

@socketio.on('log_audit_event')
def handle_audit_event(data):
    # This handler now implicitly broadcasts via the modified audit_log.log_event
    session_id = request.sid
    session_name = chat_sessions.get(session_id, {}).get('name')
    audit_log.log_event(
        event=data.get('event'),
        session_id=session_id,
        session_name=session_name,
        source=data.get('source'),
        destination=data.get('destination'),
        observers=data.get('observers'),
        details=data.get('details')
    )

@socketio.on('request_session_list')
def handle_session_list_request():
    session_id = request.sid
    session_name = chat_sessions.get(session_id, {}).get('name')
    audit_log.log_event("Socket.IO Event Received: request_session_list", session_id=session_id, session_name=session_name, source="Client", destination="Server", observers=["Orchestrator"])
    tool_result = execute_tool_command({'action': 'list_sessions'}, socketio, session_id, chat_sessions, model)
    audit_log.log_event("Socket.IO Emit: session_list_update", session_id=session_id, session_name=session_name, source="Server", destination="Client", observers=["User"], details=tool_result)
    socketio.emit('session_list_update', tool_result, to=request.sid)

@socketio.on('request_api_stats')
def handle_api_stats_request():
    session_id = request.sid
    session_name = chat_sessions.get(session_id, {}).get('name')
    audit_log.log_event("Socket.IO Event Received: request_api_stats", session_id=session_id, session_name=session_name, source="Client", destination="Server", observers=["Orchestrator"])
    audit_log.log_event("Socket.IO Emit: api_usage_update", session_id=session_id, session_name=session_name, source="Server", destination="Client", observers=["User"], details=api_stats)
    socketio.emit('api_usage_update', api_stats, to=request.sid)

@socketio.on('request_session_name')
def handle_session_name_request():
    session_id = request.sid
    session_name = chat_sessions.get(session_id, {}).get('name')
    audit_log.log_event("Socket.IO Event Received: request_session_name", session_id=session_id, session_name=session_name, source="Client", destination="Server", observers=["Orchestrator"])
    session_data = chat_sessions.get(session_id)
    if session_data:
        name = session_data.get('name')
        audit_log.log_event("Socket.IO Emit: session_name_update", session_id=session_id, session_name=name, source="Server", destination="Client", observers=["User"], details={'name': name})
        socketio.emit('session_name_update', {'name': name}, to=request.sid)
        
# --- NEW: Socket.IO handlers for Database Viewer ---
@socketio.on('request_db_collections')
def handle_db_collections_request():
    session_id = request.sid
    session_name = chat_sessions.get(session_id, {}).get('name', 'N/A')
    audit_log.log_event(
        "DB Viewer: Collections Requested", 
        session_id=session_id, 
        session_name=session_name,
        source="Database Viewer", 
        destination="Server"
    )
    collections_json = db_inspector.list_collections_as_json()
    socketio.emit('db_collections_list', collections_json, to=session_id)
    audit_log.log_event(
        "DB Viewer: Collections Sent", 
        session_id=session_id, 
        session_name=session_name,
        source="Server", 
        destination="Database Viewer",
        details=json.loads(collections_json)
    )

@socketio.on('request_db_collection_data')
def handle_db_collection_data_request(data):
    session_id = request.sid
    session_name = chat_sessions.get(session_id, {}).get('name', 'N/A')
    collection_name = data.get('collection_name')
    audit_log.log_event(
        "DB Viewer: Collection Data Requested", 
        session_id=session_id, 
        session_name=session_name,
        source="Database Viewer", 
        destination="Server",
        details={'collection_name': collection_name}
    )
    if collection_name:
        collection_data_json = db_inspector.get_collection_data_as_json(collection_name)
        socketio.emit('db_collection_data', collection_data_json, to=session_id)
        audit_log.log_event(
            "DB Viewer: Collection Data Sent", 
            session_id=session_id, 
            session_name=session_name,
            source="Server", 
            destination="Database Viewer",
            details={'collection_name': collection_name} # Don't log full data
        )

@socketio.on('user_confirmation')
def handle_user_confirmation(data):
    session_id = request.sid
    session_name = chat_sessions.get(session_id, {}).get('name')
    audit_log.log_event("Socket.IO Event Received: user_confirmation", session_id=session_id, session_name=session_name, source="Client", destination="Server", observers=["Orchestrator"], details=data)
    event = confirmation_events.get(session_id)
    if event:
        event.send(data.get('response'))

if __name__ == '__main__':
    if not API_KEY:
        app.logger.critical("Server startup failed: API key is missing.")
    else:
        # --- ACTIVATE THIS BLOCK FOR DEBUGGING ---
        if False:
            debugpy.listen(("0.0.0.0", 5678))
            app.logger.info("Debugpy server listening on port 5678. Waiting for debugger to attach...")
            debugpy.wait_for_client()
            app.logger.info("Debugger attached.")

        app.logger.info("Starting Unified Agent Server on http://127.0.0.1:5001")
        audit_log.log_event("SocketIO Server Started", source="System", destination="System", observers=["Orchestrator"])
        socketio.run(app, port=5001)
