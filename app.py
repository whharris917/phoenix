from flask import Flask, jsonify, request, render_template, send_from_directory
from flask_socketio import SocketIO
from flask_cors import CORS
import google.generativeai as genai
import os
import io
import sys
from contextlib import redirect_stdout
import json
import logging
import time
import random

# --- Function to load API key from a file ---
def load_api_key():
    """Safely loads the API key from an untracked file."""
    try:
        key_path = os.path.join(os.path.dirname(__file__), 'private_data', 'Gemini_API_Key.txt')
        with open(key_path, 'r') as f:
            return f.read().strip()
    except FileNotFoundError:
        logging.error("CRITICAL: API key file not found at 'private_data/Gemini_API_Key.txt'")
        return None
    except Exception as e:
        logging.error(f"CRITICAL: An error occurred while reading the API key file: {e}")
        return None

# --- NEW: Function to load the system prompt from a file ---
def load_system_prompt():
    """Loads the system prompt from an external text file."""
    try:
        prompt_path = os.path.join(os.path.dirname(__file__), 'public_data', 'system_prompt.txt')
        with open(prompt_path, 'r') as f:
            return f.read()
    except FileNotFoundError:
        logging.error("CRITICAL: System prompt file not found at 'public_data/system_prompt.txt'")
        return "You are a helpful assistant." # Fallback prompt
    except Exception as e:
        logging.error(f"CRITICAL: An error occurred while reading the system prompt file: {e}")
        return "You are a helpful assistant."

# --- CONFIGURATION ---
API_KEY = load_api_key()
SYSTEM_PROMPT = load_system_prompt()
SESSIONS_FILE = os.path.join(os.path.dirname(__file__), 'sandbox', 'sessions', 'sessions.json')
app = Flask(__name__)
CORS(app)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='eventlet')

# --- Setup Logging ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("agent.log"),
        logging.StreamHandler()
    ]
)

# --- GEMINI SETUP ---
model = None
if API_KEY:
    try:
        genai.configure(api_key=API_KEY)
        model = genai.GenerativeModel(
            model_name='gemini-2.5-pro',
            system_instruction=SYSTEM_PROMPT
        )
        logging.info("Gemini API configured successfully.")
    except Exception as e:
        logging.critical(f"FATAL: Failed to configure Gemini API with the provided key. Error: {e}")
else:
    logging.critical("FATAL: Gemini API key not loaded. The application cannot connect to the AI model.")


# --- Dictionary to store chat sessions for each user ---
chat_sessions = {}

# --- TOOL AGENT LOGIC ---
def get_safe_path(filename):
    base_dir = os.path.dirname(os.path.abspath(__file__))
    sandbox_dir = os.path.join(base_dir, 'sandbox')
    if not os.path.exists(sandbox_dir):
        os.makedirs(sandbox_dir)
    requested_path = os.path.abspath(os.path.join(sandbox_dir, filename))
    if os.path.commonpath([requested_path, sandbox_dir]) != sandbox_dir:
        raise ValueError("Attempted path traversal outside of sandbox.")
    return requested_path

def execute_tool_command(command, session_id):
    action = command.get('action')
    params = command.get('parameters', {})
    try:
        if action == 'create_file':
            filename = params.get('filename', 'default.txt')
            content = params.get('content', '') 
            safe_path = get_safe_path(filename)
            with open(safe_path, 'w') as f:
                f.write(content)
            return {"status": "success", "message": f"File '{filename}' created in sandbox."}
        elif action == 'read_file':
            filename = params.get('filename')
            safe_path = get_safe_path(filename)
            if not os.path.exists(safe_path):
                return {"status": "error", "message": f"File '{filename}' not found."}
            with open(safe_path, 'r') as f:
                content = f.read()
            return {"status": "success", "message": f"Read content from '{filename}'.", "content": content}
        elif action == 'list_directory':
            sandbox_dir = get_safe_path('').rsplit(os.sep, 1)[0]
            files = [f for f in os.listdir(sandbox_dir) if os.path.isfile(os.path.join(sandbox_dir, f))]
            return {"status": "success", "message": "Listed files in sandbox.", "files": files}
        elif action == 'execute_python_script':
            script_content = params.get('script_content', '')
            restricted_globals = {"__builtins__": {"print": print, "range": range, "len": len, "str": str, "int": int, "float": float, "list": list, "dict": dict, "set": set, "abs": abs, "max": max, "min": min, "sum": sum}}
            string_io = io.StringIO()
            with redirect_stdout(string_io):
                exec(script_content, restricted_globals, {})
            output = string_io.getvalue()
            return {"status": "success", "message": "Script executed.", "output": output}
        
        elif action == 'save_session':
            session_name = params.get('session_name')
            chat = chat_sessions.get(session_id)
            if not session_name or not chat:
                return {"status": "error", "message": "Session name or active chat not found."}
            
            history_to_save = [{"role": part.role, "parts": [part.parts[0].text]} for part in chat.history]
            
            summary_prompt = "Please provide a very short, one-line summary of this conversation."
            summary_response = chat.send_message(summary_prompt)
            summary = summary_response.text

            os.makedirs(os.path.dirname(SESSIONS_FILE), exist_ok=True)
            try:
                with open(SESSIONS_FILE, 'r') as f:
                    all_sessions = json.load(f)
            except (FileNotFoundError, json.JSONDecodeError):
                all_sessions = {}
            
            all_sessions[session_name] = {"summary": summary, "history": history_to_save}

            with open(SESSIONS_FILE, 'w') as f:
                json.dump(all_sessions, f, indent=4)
            
            return {"status": "success", "message": f"Session '{session_name}' saved."}

        elif action == 'list_sessions':
            try:
                with open(SESSIONS_FILE, 'r') as f:
                    all_sessions = json.load(f)
                session_list = [{"name": name, "summary": data.get("summary")} for name, data in all_sessions.items()]
                return {"status": "success", "sessions": session_list}
            except (FileNotFoundError, json.JSONDecodeError):
                return {"status": "success", "sessions": []}

        elif action == 'load_session':
            session_name = params.get('session_name')
            try:
                with open(SESSIONS_FILE, 'r') as f:
                    all_sessions = json.load(f)
                
                session_data = all_sessions.get(session_name)
                if not session_data:
                    return {"status": "error", "message": f"Session '{session_name}' not found."}
                
                history = [{'role': item['role'], 'parts': item['parts']} for item in session_data['history']]
                
                chat_sessions[session_id] = model.start_chat(history=history)
                return {"status": "success", "message": f"Session '{session_name}' loaded."}
            except (FileNotFoundError, json.JSONDecodeError):
                return {"status": "error", "message": "No saved sessions found."}
        
        else:
            return {"status": "error", "message": "Unknown action"}
    except Exception as e:
        logging.error(f"Error executing tool command: {e}")
        return {"status": "error", "message": f"An error occurred: {e}"}

# --- ORCHESTRATOR LOGIC ---
def execute_reasoning_loop(chat, initial_prompt, session_id):
    try:
        current_prompt = initial_prompt
        for i in range(5):
            socketio.sleep(0)
            response = chat.send_message(current_prompt)
            response_text = response.text
            if "{" in response_text and "}" in response_text:
                command_json = json.loads(response_text.strip().replace('```json', '').replace('```', ''))
                action = command_json.get("action")
                socketio.emit('log_message', {'type': 'thought', 'data': f"I should use the '{action}' tool."})
                socketio.emit('agent_action', {'type': 'Executing', 'data': command_json})
                
                socketio.sleep(0.1)
                tool_result = execute_tool_command(command_json, session_id)
                
                socketio.emit('agent_action', {'type': 'Result', 'data': tool_result})
                current_prompt = f"TOOL_RESULT: {json.dumps(tool_result)}"
            else:
                socketio.sleep(0.1)
                socketio.emit('log_message', {'type': 'final_answer', 'data': response_text})
                return
    except Exception as e:
        logging.exception("An error occurred in the reasoning loop.")
        socketio.emit('log_message', {'type': 'error', 'data': f"An error occurred during reasoning: {str(e)}"})

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

@socketio.on('connect')
def handle_connect():
    app.logger.info(f"Client connected: {request.sid}")
    if model is None:
        app.logger.error("Model not initialized. Cannot create chat session.")
        socketio.emit('log_message', {'type': 'error', 'data': 'AI model is not available. Check server logs.'}, to=request.sid)
        return

    try:
        chat_sessions[request.sid] = model.start_chat(history=[])
        app.logger.info(f"Chat session created for {request.sid}")
    except Exception as e:
        app.logger.exception(f"Could not create chat session for {request.sid}.")
        socketio.emit('log_message', {'type': 'error', 'data': f'Failed to initialize AI session. Check server logs for details.'}, to=request.sid)

@socketio.on('disconnect')
def handle_disconnect():
    app.logger.info(f"Client disconnected: {request.sid}")
    chat_sessions.pop(request.sid, None)

@socketio.on('start_task')
def handle_start_task(data):
    prompt = data.get('prompt')
    session_id = request.sid
    chat = chat_sessions.get(session_id)
    if prompt and chat:
        socketio.emit('log_message', {'type': 'system', 'data': 'Task received. Starting reasoning process...'})
        socketio.start_background_task(execute_reasoning_loop, chat, prompt, session_id)
    elif not chat:
        app.logger.warning(f"Task from {session_id} rejected because no chat session exists.")
        socketio.emit('log_message', {'type': 'error', 'data': 'No active AI session. Please refresh.'}, to=request.sid)

@socketio.on('request_sandbox_refresh')
def handle_sandbox_refresh():
    result = execute_tool_command({'action': 'list_directory'}, None)
    socketio.emit('sandbox_update', result, to=request.sid)

@socketio.on('request_session_list')
def handle_session_list_request():
    result = execute_tool_command({'action': 'list_sessions'}, None)
    socketio.emit('session_list_update', result, to=request.sid)

if __name__ == '__main__':
    if not API_KEY:
        app.logger.critical("Server startup failed: API key is missing. Please create 'private_data/Gemini_API_Key.txt'.")
    else:
        app.logger.info("Starting Unified Agent Server on http://127.0.0.1:5001")
        socketio.run(app, port=5001)
