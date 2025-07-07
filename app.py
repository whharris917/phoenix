from flask import Flask, jsonify, request, render_template, send_from_directory
from flask_socketio import SocketIO
from flask_cors import CORS
import google.generativeai as genai
import os
import time
import random
import io
import sys
from contextlib import redirect_stdout
import json # <-- THE MISSING IMPORT

# --- CONFIGURATION ---
API_KEY = "AIzaSyALFegx2Gslr5a-xzx1sLWFOzB1EQ0xVZY"
app = Flask(__name__)
CORS(app)
socketio = SocketIO(app, cors_allowed_origins="*")

# --- GEMINI SETUP ---
genai.configure(api_key=API_KEY)
model = genai.GenerativeModel(
    model_name='gemini-2.5-pro',
    system_instruction="""
You are "Agent Control," an AI assistant that reasons and uses tools to answer user questions about local files and perform calculations.
Your goal is to answer the user's question fully. To do this, you can use tools in a step-by-step manner.
At each step, you will respond with a single JSON command to use one of your available tools. I will execute it and return the result to you as "TOOL_RESULT: ...".
You will then use that result to decide on the next step, which could be using another tool or, if you have enough information, providing the final answer in plain text.

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
        return {"status": "error", "message": f"Script error: {e}"}

# --- ORCHESTRATOR LOGIC ---
def execute_reasoning_loop(initial_prompt):
    try:
        chat = model.start_chat(history=[])
        current_prompt = initial_prompt
        for i in range(5):
            time.sleep(random.uniform(0.4, 0.8))
            response = chat.send_message(current_prompt)
            response_text = response.text
            if "{" in response_text and "}" in response_text:
                command_json = json.loads(response_text.strip().replace('```json', '').replace('```', ''))
                action = command_json.get("action")
                socketio.emit('log_message', {'type': 'thought', 'data': f"I should use the '{action}' tool."})
                socketio.emit('agent_action', {'type': 'Executing', 'data': command_json})
                time.sleep(0.4)
                tool_result = execute_tool_command(command_json)
                socketio.emit('agent_action', {'type': 'Result', 'data': tool_result})
                current_prompt = f"TOOL_RESULT: {json.dumps(tool_result)}"
            else:
                time.sleep(0.5)
                socketio.emit('log_message', {'type': 'final_answer', 'data': response_text})
                return
    except Exception as e:
        socketio.emit('log_message', {'type': 'error', 'data': f"An error occurred: {str(e)}"})

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

@socketio.on('start_task')
def handle_start_task(data):
    prompt = data.get('prompt')
    if prompt:
        socketio.emit('log_message', {'type': 'system', 'data': 'Task received. Starting reasoning process...'})
        socketio.start_background_task(execute_reasoning_loop, prompt)

if __name__ == '__main__':
    print("Unified Agent Server is running on http://127.0.0.1:5001")
    socketio.run(app, port=5001)
