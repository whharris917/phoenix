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

# --- NEW: Function to load API key from a file ---
def load_api_key():
    """Safely loads the API key from an untracked file."""
    try:
        # The path is constructed relative to the location of this script
        key_path = os.path.join(os.path.dirname(__file__), 'private_data', 'Gemini_API_Key.txt')
        with open(key_path, 'r') as f:
            # Read the key and remove leading/trailing whitespace
            return f.read().strip()
    except FileNotFoundError:
        logging.error("CRITICAL: API key file not found at 'private_data/Gemini_API_Key.txt'")
        return None
    except Exception as e:
        logging.error(f"CRITICAL: An error occurred while reading the API key file: {e}")
        return None

# --- CONFIGURATION ---
API_KEY = load_api_key() # Load the key using our new function
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
            system_instruction="""
You are "Agent Control," an AI assistant that reasons and uses tools to answer user questions.

Your goal is to answer the user's question fully and efficiently. At each step, you have a choice:

1.  **Answer Directly**: If you can answer the user's query using your own internal knowledge or the conversation history without needing access to the local file system, then provide the answer directly in plain text.

2.  **Use a Tool**: If you need to interact with the local file system to get information or perform an action, then respond with a single JSON command for one of the available tools. I will execute it and return the result to you as "TOOL_RESULT: ...".

## Reasoning Strategy
- When asked to perform a task that requires multiple steps (like writing, executing, and then saving a script), break it down into a sequence of tool calls.
- **Example Strategy**: If asked to "write and run a script to do X and save it", your plan should be:
    1. First, use the `execute_python_script` tool to run the code and get the result.
    2. After you receive the successful execution result, use the `create_file` tool in the next step to save the script you just ran.
    3. Finally, report the result of the execution to the user.

## Available Tools:
1.  **Action: `read_file`**
    * JSON Format: {"action": "read_file", "parameters": {"filename": "<name>"}}
2.  **Action: `list_directory`**
    * JSON Format: {"action": "list_directory", "parameters": {}}
3.  **Action: `create_file`**
    * JSON Format: {"action": "create_file", "parameters": {"filename": "<name>", "content": "<content>"}}
4.  **Action: `execute_python_script`**
    * JSON Format: {"action": "execute_python_script", "parameters": {"script_content": "<python_code>"}}
"""
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
    return requested_path, sandbox_dir

def execute_tool_command(command):
    action = command.get('action')
    params = command.get('parameters', {})
    try:
        if action == 'create_file':
            filename = params.get('filename', 'default.txt')
            content = params.get('content', '') 
            safe_path, _ = get_safe_path(filename)
            with open(safe_path, 'w') as f:
                f.write(content)
            return {"status": "success", "message": f"File '{filename}' created in sandbox."}
        elif action == 'read_file':
            filename = params.get('filename')
            safe_path, _ = get_safe_path(filename)
            if not os.path.exists(safe_path):
                return {"status": "error", "message": f"File '{filename}' not found."}
            with open(safe_path, 'r') as f:
                content = f.read()
            return {"status": "success", "message": f"Read content from '{filename}'.", "content": content}
        elif action == 'list_directory':
            _, sandbox_dir = get_safe_path('')
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
        else:
            return {"status": "error", "message": "Unknown action"}
    except ValueError as e:
        return {"status": "security_error", "message": str(e)}
    except Exception as e:
        logging.error(f"Error executing tool command: {e}")
        return {"status": "error", "message": f"Script error: {e}"}

# --- ORCHESTRATOR LOGIC ---
def execute_reasoning_loop(chat, initial_prompt):
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
                tool_result = execute_tool_command(command_json)
                
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

@app.route('/execute', methods=['POST'])
def handle_execute():
    command_data = request.json
    result = execute_tool_command(command_data)
    return jsonify(result)

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
        socketio.start_background_task(execute_reasoning_loop, chat, prompt)
    elif not chat:
        app.logger.warning(f"Task from {session_id} rejected because no chat session exists.")
        socketio.emit('log_message', {'type': 'error', 'data': 'No active AI session. Please refresh.'}, to=request.sid)

if __name__ == '__main__':
    if not API_KEY:
        app.logger.critical("Server startup failed: API key is missing.")
    else:
        app.logger.info("Starting Unified Agent Server on http://127.0.0.1:5001")
        socketio.run(app, port=5001)
