import os
import io
import sys
from contextlib import redirect_stdout
import json
import logging
from eventlet import tpool
# --- NEW: Import the code parser ---
from code_parser import analyze_codebase, generate_mermaid_diagram

# --- Constants ---
SESSIONS_FILE = os.path.join(os.path.dirname(__file__), 'sandbox', 'sessions', 'sessions.json')
ALLOWED_PROJECT_FILES = [
    'app.py',
    'orchestrator.py',
    'tool_agent.py',
    'public_data/system_prompt.txt',
    'index.html',
    'workshop.html',
    'documentation_viewer.html',
    'code_parser.py' # Add the new file to the allowed list
]

# --- Helper functions (no changes) ---

def _execute_script(script_content):
    string_io = io.StringIO()
    try:
        restricted_globals = {"__builtins__": {"print": print, "range": range, "len": len, "str": str, "int": int, "float": float, "list": list, "dict": dict, "set": set, "abs": abs, "max": max, "min": min, "sum": sum}}
        with redirect_stdout(string_io):
            exec(script_content, restricted_globals, {})
        return {"status": "success", "output": string_io.getvalue()}
    except Exception as e:
        return {"status": "error", "message": str(e)}

def _write_file(path, content):
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w') as f:
            f.write(content)
        return {"status": "success"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

def _read_file(path):
    try:
        if not os.path.exists(path):
            return {"status": "error", "message": "File not found."}
        with open(path, 'r') as f:
            content = f.read()
        return {"status": "success", "content": content}
    except Exception as e:
        return {"status": "error", "message": str(e)}

def _delete_file(path):
    try:
        if not os.path.exists(path):
            return {"status": "error", "message": "File not found."}
        os.remove(path)
        return {"status": "success"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

def _list_directory(path):
    try:
        file_list = []
        for root, dirs, files in os.walk(path):
            if 'sessions' in dirs:
                dirs.remove('sessions')
            for name in files:
                relative_path = os.path.relpath(os.path.join(root, name), path)
                file_list.append(relative_path.replace('\\', '/'))
        return {"status": "success", "files": file_list}
    except Exception as e:
        return {"status": "error", "message": str(e)}

def _read_sessions_file(path):
    try:
        with open(path, 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

def _write_sessions_file(path, data):
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w') as f:
            json.dump(data, f, indent=4)
        return {"status": "success"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

# --- Core Tooling Logic ---

def get_safe_path(filename, base_dir_name='sandbox'):
    base_dir = os.path.dirname(os.path.abspath(__file__))
    target_dir = os.path.join(base_dir, base_dir_name)
    if not os.path.exists(target_dir):
        os.makedirs(target_dir)
    
    requested_path = os.path.abspath(os.path.join(target_dir, filename))
    
    if not requested_path.startswith(target_dir):
        raise ValueError("Attempted path traversal outside of allowed directory.")
    return requested_path

def execute_tool_command(command, session_id, chat_sessions, model):
    action = command.get('action')
    params = command.get('parameters', {})
    try:
        # ... (all other actions remain the same)
        if action == 'create_file':
            filename = params.get('filename', 'default.txt')
            content = params.get('content', '') 
            safe_path = get_safe_path(filename)
            result = tpool.execute(_write_file, safe_path, content)
            if result['status'] == 'success':
                return {"status": "success", "message": f"File '{filename}' created in sandbox."}
            else:
                return {"status": "error", "message": f"Failed to create file: {result['message']}"}
        
        elif action == 'read_file':
            filename = params.get('filename')
            safe_path = get_safe_path(filename)
            result = tpool.execute(_read_file, safe_path)
            if result['status'] == 'success':
                return {"status": "success", "message": f"Read content from '{filename}'.", "content": result['content']}
            else:
                return {"status": "error", "message": result['message']}
        
        elif action == 'read_project_file':
            filename = params.get('filename')
            if filename not in ALLOWED_PROJECT_FILES:
                return {"status": "error", "message": f"Access denied. Reading the project file '{filename}' is not permitted."}
            project_file_path = os.path.join(os.path.dirname(__file__), filename)
            result = tpool.execute(_read_file, project_file_path)
            if result['status'] == 'success':
                return {"status": "success", "message": f"Read content from project file '{filename}'.", "content": result['content']}
            else:
                return {"status": "error", "message": result['message']}

        elif action == 'list_allowed_project_files':
            return {"status": "success", "message": "Listed allowed project files.", "allowed_files": ALLOWED_PROJECT_FILES}

        elif action == 'list_directory':
            sandbox_dir = get_safe_path('').rsplit(os.sep, 1)[0]
            result = tpool.execute(_list_directory, sandbox_dir)
            if result['status'] == 'success':
                 return {"status": "success", "message": "Listed files in sandbox.", "files": result['files']}
            else:
                return {"status": "error", "message": f"Failed to list directory: {result['message']}"}

        elif action == 'delete_file':
            filename = params.get('filename')
            safe_path = get_safe_path(filename)
            result = tpool.execute(_delete_file, safe_path)
            if result['status'] == 'success':
                return {"status": "success", "message": f"File '{filename}' deleted."}
            else:
                return {"status": "error", "message": result['message']}

        elif action == 'execute_python_script':
            script_content = params.get('script_content', '')
            result = tpool.execute(_execute_script, script_content)
            if result['status'] == 'success':
                return {"status": "success", "message": "Script executed.", "output": result['output']}
            else:
                return {"status": "error", "message": f"An error occurred in script: {result['message']}"}

        # --- NEW VISUALIZER TOOL ---
        elif action == 'generate_code_diagram':
            try:
                project_root = os.path.dirname(__file__)
                files_to_analyze = [
                    os.path.join(project_root, 'app.py'),
                    os.path.join(project_root, 'orchestrator.py'),
                    os.path.join(project_root, 'tool_agent.py')
                ]
                
                code_structure = analyze_codebase(files_to_analyze)
                mermaid_code = generate_mermaid_diagram(code_structure)
                
                output_filename = 'code_flow.md'
                safe_output_path = get_safe_path(output_filename)
                write_result = tpool.execute(_write_file, safe_output_path, mermaid_code)

                if write_result['status'] == 'success':
                    return {"status": "success", "message": f"Code flow diagram generated and saved to '{output_filename}'."}
                else:
                    return {"status": "error", "message": f"Failed to save diagram: {write_result['message']}"}
            except Exception as e:
                logging.error(f"Error generating code diagram: {e}")
                return {"status": "error", "message": str(e)}

        # ... (session management tools remain the same)
        elif action == 'save_session':
            session_name = params.get('session_name')
            session_data = chat_sessions.get(session_id)
            if not session_name or not session_data:
                return {"status": "error", "message": "Session name or active chat not found."}
            chat = session_data.get('chat') if isinstance(session_data, dict) else session_data
            if not chat:
                 return {"status": "error", "message": "Chat object not found in session."}
            history_to_save = []
            for part in chat.history:
                history_to_save.append({
                    "role": part.role,
                    "parts": [{'text': p.text} for p in part.parts]
                })
            all_sessions = tpool.execute(_read_sessions_file, SESSIONS_FILE)
            all_sessions[session_name] = {"summary": "Saved Session", "history": history_to_save}
            write_result = tpool.execute(_write_sessions_file, SESSIONS_FILE, all_sessions)
            if write_result['status'] == 'success':
                return {"status": "success", "message": f"Session '{session_name}' saved."}
            else:
                return {"status": "error", "message": f"Failed to save session: {write_result['message']}"}

        elif action == 'list_sessions':
            all_sessions = tpool.execute(_read_sessions_file, SESSIONS_FILE)
            session_list = []
            for name, data in all_sessions.items():
                if isinstance(data, dict):
                    summary = data.get("summary", "No summary available.")
                    session_list.append({"name": name, "summary": summary})
            return {"status": "success", "sessions": session_list}

        elif action == 'load_session':
            session_name = params.get('session_name')
            all_sessions = tpool.execute(_read_sessions_file, SESSIONS_FILE)
            session_data_to_load = all_sessions.get(session_name)
            if not session_data_to_load:
                return {"status": "error", "message": f"Session '{session_name}' not found."}
            history = session_data_to_load.get('history', [])
            chat_sessions[session_id] = {
                "chat": model.start_chat(history=history),
                "name": session_name
            }
            return {"status": "success", "message": f"Session '{session_name}' loaded.", "history": history}
        
        elif action == 'delete_session':
            session_name = params.get('session_name')
            all_sessions = tpool.execute(_read_sessions_file, SESSIONS_FILE)
            if session_name not in all_sessions:
                 return {"status": "error", "message": f"Session '{session_name}' not found."}
            del all_sessions[session_name]
            write_result = tpool.execute(_write_sessions_file, SESSIONS_FILE, all_sessions)
            if write_result['status'] == 'success':
                return {"status": "success", "message": f"Session '{session_name}' deleted."}
            else:
                return {"status": "error", "message": f"Failed to delete session: {write_result['message']}"}
        
        else:
            return {"status": "error", "message": "Unknown action"}

    except Exception as e:
        logging.error(f"Error executing tool command: {e}")
        return {"status": "error", "message": f"An error occurred: {e}"}
