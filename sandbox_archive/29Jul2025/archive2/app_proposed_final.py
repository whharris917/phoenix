from flask import Flask, render_template, send_from_directory, request, jsonify
from flask_socketio import SocketIO
from flask_cors import CORS
import os
import logging
import json
from datetime import datetime
from orchestrator import execute_reasoning_loop, confirmation_events
# REFINED: Import the wrapper from tool_agent
from tool_agent import execute_tool_command, get_safe_path, HavenProxyWrapper
from memory_manager import MemoryManager
from multiprocessing.managers import BaseManager
from audit_logger import audit_log
import inspect_db as db_inspector
import debugpy
import time

# --- CONFIGURATION ---
app = Flask(__name__)
CORS(app)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='eventlet')
audit_log.register_socketio(socketio)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s', handlers=[logging.FileHandler("agent.log"), logging.StreamHandler()])

# --- HAVEN SETUP ---
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
    logging.critical("FATAL: Could not connect to Haven. The application cannot function without it.")

# This dictionary holds session-specific data for currently connected clients.
chat_sessions = {}

# --- SERVER ROUTES & EVENTS (Unchanged) ---
@app.route('/')
def serve_index():
    return send_from_directory('.', 'index.html')

@app.route('/audit_visualizer')
def serve_audit_visualizer():
    return send_from_directory('.', 'audit_visualizer.html')

@app.route('/database_viewer')
def serve_database_viewer():
    return send_from_directory('.', 'database_viewer.html')

@app.route('/docs')
def serve_docs():
    return send_from_directory('.', 'documentation_viewer.html')

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
            memory = MemoryManager(session_name=new_session_name)
            
            # Use the imported HavenProxyWrapper
            chat_wrapper = HavenProxyWrapper(haven_proxy, new_session_name)
            chat_sessions[session_id] = {
                "chat": chat_wrapper,
                "memory": memory,
                "name": new_session_name
            }
            app.logger.info(f"Local session stub created for {session_id} with name {new_session_name}")
            
            socketio.emit('session_name_update', {'name': new_session_name}, to=session_id)
            
            # Restore history rendering
            full_history = memory.get_full_history()
            if full_history:
                history_for_client = [
                    {"role": c.role, "parts": [{"text": p.text} for p in c.parts]} for c in full_history
                ]
                audit_log.log_event("Socket.IO Emit: full_history_update", session_id=session_id, session_name=new_session_name, source="Application", destination="Client", details=f"{len(history_for_client)} turns loaded")
                socketio.emit('load_chat_history', {'history': history_for_client}, to=session_id)

        except Exception as e:
            app.logger.exception(f"Could not create local session stub for {session_id}: {e}")
            socketio.emit('log_message', {'type': 'error', 'data': 'Failed to initialize session.'}, to=session_id)
    else:
        socketio.emit('log_message', {'type': 'error', 'data': 'Haven service not available.'}, to=request.sid)

@socketio.on('disconnect')
def handle_disconnect():
    session_id = request.sid
    if session_id in chat_sessions:
        session_name = chat_sessions[session_id].get('name')
        app.logger.info(f"Client disconnected: {session_id}, Session: {session_name}")
        chat_sessions.pop(session_id, None)
        confirmation_events.pop(session_id, None)

@socketio.on('start_task')
def handle_start_task(data):
    session_id = request.sid
    session_data = chat_sessions.get(session_id)
    if not session_data:
        socketio.emit('log_message', {'type': 'error', 'data': 'No active session. Please refresh.'}, to=request.sid)
        return
        
    prompt = data.get('prompt')
    if prompt:
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        timestamped_prompt = f"[{timestamp}] {prompt}"
        socketio.emit('display_user_prompt', {'prompt': timestamped_prompt}, to=session_id)
        socketio.start_background_task(execute_reasoning_loop, socketio, session_data, timestamped_prompt, session_id, chat_sessions, haven_proxy)

@socketio.on('request_session_list')
def handle_session_list_request():
    session_id = request.sid
    tool_result = execute_tool_command({'action': 'list_sessions'}, socketio, session_id, chat_sessions, haven_proxy)
    socketio.emit('session_list_update', tool_result, to=request.sid)

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
        socketio.run(app, port=5001)