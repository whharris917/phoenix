from flask import Flask, render_template, send_from_directory, request, jsonify
from flask_socketio import SocketIO
from flask_cors import CORS
import os
import logging
import json
from datetime import datetime
from orchestrator import execute_reasoning_loop, confirmation_events
from tool_agent import execute_tool_command, get_safe_path, HavenProxyWrapper
from memory_manager import MemoryManager
from multiprocessing.managers import BaseManager
import inspect_db as db_inspector
import debugpy
import time

# --- CONFIGURATION ---
app = Flask(__name__)
CORS(app)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='eventlet')
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

# --- SERVER ROUTES & EVENTS ---
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

@socketio.on('request_session_name')
def handle_session_name_request():
    session_id = request.sid
    session_name = chat_sessions.get(session_id, {}).get('name')
    session_data = chat_sessions.get(session_id)
    if session_data:
        name = session_data.get('name')
        socketio.emit('session_name_update', {'name': name}, to=request.sid)
        
# --- NEW: Socket.IO handlers for Database Viewer ---
@socketio.on('request_db_collections')
def handle_db_collections_request():
    session_id = request.sid
    session_name = chat_sessions.get(session_id, {}).get('name', 'N/A')
    collections_json = db_inspector.list_collections_as_json()
    socketio.emit('db_collections_list', collections_json, to=session_id)

@socketio.on('request_db_collection_data')
def handle_db_collection_data_request(data):
    session_id = request.sid
    session_name = chat_sessions.get(session_id, {}).get('name', 'N/A')
    collection_name = data.get('collection_name')
    if collection_name:
        collection_data_json = db_inspector.get_collection_data_as_json(collection_name)
        socketio.emit('db_collection_data', collection_data_json, to=session_id)

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
        # --- ACTIVATE THIS BLOCK FOR DEBUGGING ---
        # use this: debugpy.breakpoint()
        if False:
            debugpy.listen(("0.0.0.0", 5678))
            app.logger.info("Debugpy server listening on port 5678. Waiting for debugger to attach...")
            debugpy.wait_for_client()
            app.logger.info("Debugger attached.")

        app.logger.info("Starting Unified Agent Server on http://127.0.0.1:5001")
        socketio.run(app, port=5001)
