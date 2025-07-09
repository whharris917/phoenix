from flask import Flask, render_template, send_from_directory, request
from flask_socketio import SocketIO
from flask_cors import CORS
import google.generativeai as genai
import os
import logging
from orchestrator import execute_reasoning_loop, confirmation_events
from tool_agent import execute_tool_command

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
        return "You are a helpful assistant."

# --- CONFIGURATION ---
API_KEY = load_api_key()
SYSTEM_PROMPT = load_system_prompt()
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
        model = genai.GenerativeModel(model_name='gemini-2.5-pro', system_instruction=SYSTEM_PROMPT)
        logging.info("Gemini API configured successfully.")
    except Exception as e:
        logging.critical(f"FATAL: Failed to configure Gemini API. Error: {e}")
else:
    logging.critical("FATAL: Gemini API key not loaded.")

chat_sessions = {}

# --- SERVER ROUTES & EVENTS ---
@app.route('/')
def serve_index():
    return send_from_directory('.', 'index.html')

@app.route('/docs')
def serve_docs():
    return send_from_directory('.', 'documentation_viewer.html')

@app.route('/documentation.md')
def serve_markdown():
    return send_from_directory('.', 'documentation.md')

# --- NEW: Route to serve the workshop page ---
@app.route('/workshop')
def serve_workshop():
    return send_from_directory('.', 'workshop.html')

@socketio.on('connect')
def handle_connect():
    app.logger.info(f"Client connected: {request.sid}")
    if model:
        try:
            chat_sessions[request.sid] = model.start_chat(history=[])
            app.logger.info(f"Chat session created for {request.sid}")
        except Exception as e:
            app.logger.exception(f"Could not create chat session for {request.sid}.")
            socketio.emit('log_message', {'type': 'error', 'data': 'Failed to initialize AI session.'}, to=request.sid)
    else:
        socketio.emit('log_message', {'type': 'error', 'data': 'AI model not available.'}, to=request.sid)

@socketio.on('disconnect')
def handle_disconnect():
    app.logger.info(f"Client disconnected: {request.sid}")
    chat_sessions.pop(request.sid, None)
    confirmation_events.pop(request.sid, None)

@socketio.on('start_task')
def handle_start_task(data):
    prompt = data.get('prompt')
    session_id = request.sid
    chat = chat_sessions.get(session_id)
    if prompt and chat:
        socketio.emit('log_message', {'type': 'system', 'data': 'Task received. Starting reasoning process...'})
        socketio.start_background_task(execute_reasoning_loop, socketio, chat, prompt, session_id, chat_sessions, model)
    elif not chat:
        socketio.emit('log_message', {'type': 'error', 'data': 'No active AI session. Please refresh.'}, to=request.sid)

@socketio.on('request_sandbox_refresh')
def handle_sandbox_refresh():
    result = execute_tool_command({'action': 'list_directory'}, None, None, None)
    socketio.emit('sandbox_update', result, to=request.sid)

@socketio.on('request_session_list')
def handle_session_list_request():
    result = execute_tool_command({'action': 'list_sessions'}, None, None, None)
    socketio.emit('session_list_update', result, to=request.sid)

@socketio.on('user_confirmation')
def handle_user_confirmation(data):
    session_id = request.sid
    event = confirmation_events.get(session_id)
    if event:
        event.send(data.get('response'))

if __name__ == '__main__':
    if not API_KEY:
        app.logger.critical("Server startup failed: API key is missing.")
    else:
        app.logger.info("Starting Unified Agent Server on http://127.0.0.1:5001")
        socketio.run(app, port=5001)