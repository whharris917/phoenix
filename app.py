from flask import Flask, render_template, send_from_directory, request, jsonify
from flask_socketio import SocketIO
from flask_cors import CORS
import google.generativeai as genai
import os
import logging
import json
import atexit
from datetime import datetime # --- NEW: Import datetime ---
from orchestrator import execute_reasoning_loop, confirmation_events
from tool_agent import execute_tool_command, get_safe_path
from memory_manager import MemoryManager
from audit_logger import audit_log

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
        return "You are a helpful assistant but were unable to locate system_prompt.txt, and thus do not have access to your core directives."

# --- CONFIGURATION ---
API_KEY = load_api_key()
SYSTEM_PROMPT = load_system_prompt()
API_STATS_FILE = os.path.join(os.path.dirname(__file__), 'api_usage.json')
app = Flask(__name__)
CORS(app)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='eventlet')

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
            model_name='gemini-2.5-pro',
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

# ... (other routes remain the same) ...
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


@socketio.on('connect')
def handle_connect():
    session_id = request.sid
    # --- NEW: Generate timestamped session name ---
    timestamp = datetime.now().strftime("%d%b%Y_%I%M%S%p").upper()
    new_session_name = f"New_Session_{timestamp}"
    
    audit_log.log_event("Client Connected", session_id=session_id, session_name=new_session_name, source="Client", destination="Server", observers=["Orchestrator"])
    app.logger.info(f"Client connected: {session_id}")
    if model:
        try:
            memory = MemoryManager(session_id)
            chat_sessions[session_id] = {
                "chat": model.start_chat(history=memory.get_full_history()),
                "memory": memory,
                "name": new_session_name # Use the new name
            }
            app.logger.info(f"Chat and MemoryManager session created for {session_id} with name {new_session_name}")
            audit_log.log_event("Socket.IO Emit: session_name_update", session_id=session_id, session_name=new_session_name, source="Server", destination="Client", observers=["User", "Orchestrator"], details={'name': new_session_name})
            socketio.emit('session_name_update', {'name': new_session_name}, to=session_id)
        except Exception as e:
            app.logger.exception(f"Could not create chat session for {session_id}.")
            socketio.emit('log_message', {'type': 'error', 'data': 'Failed to initialize AI session.'}, to=session_id)
    else:
        socketio.emit('log_message', {'type': 'error', 'data': 'AI model not available.'}, to=request.sid)

@socketio.on('disconnect')
def handle_disconnect():
    session_id = request.sid
    session_name = chat_sessions.get(session_id, {}).get('name')
    audit_log.log_event("Client Disconnected", session_id=session_id, session_name=session_name, source="Client", destination="Server", observers=["Orchestrator"])
    app.logger.info(f"Client disconnected: {session_id}")
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
    result = execute_tool_command({'action': 'list_sessions'}, session_id, chat_sessions, model)
    audit_log.log_event("Socket.IO Emit: session_list_update", session_id=session_id, session_name=session_name, source="Server", destination="Client", observers=["User"], details=result)
    socketio.emit('session_list_update', result, to=request.sid)

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
        app.logger.info("Starting Unified Agent Server on http://127.0.0.1:5001")
        audit_log.log_event("SocketIO Server Started", source="System", destination="System", observers=["Orchestrator"])
        socketio.run(app, port=5001)
