import os
import io
import sys
from contextlib import redirect_stdout
import json
import logging

SESSIONS_FILE = os.path.join(os.path.dirname(__file__), 'sandbox', 'sessions', 'sessions.json')

def get_safe_path(filename):
    base_dir = os.path.dirname(os.path.abspath(__file__))
    sandbox_dir = os.path.join(base_dir, 'sandbox')
    if not os.path.exists(sandbox_dir):
        os.makedirs(sandbox_dir)
    requested_path = os.path.abspath(os.path.join(sandbox_dir, filename))
    if os.path.commonpath([requested_path, sandbox_dir]) != sandbox_dir:
        raise ValueError("Attempted path traversal outside of sandbox.")
    return requested_path

def execute_tool_command(command, session_id, chat_sessions, model):
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
        elif action == 'delete_file':
            filename = params.get('filename')
            safe_path = get_safe_path(filename)
            if os.path.exists(safe_path):
                os.remove(safe_path)
                return {"status": "success", "message": f"File '{filename}' deleted."}
            else:
                return {"status": "error", "message": f"File '{filename}' not found."}
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
            
            summary_chat = model.start_chat(history=history_to_save)
            summary_prompt = "Please provide a very short, one-line summary of this conversation."
            summary_response = summary_chat.send_message(summary_prompt)
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
        
        elif action == 'delete_session':
            session_name = params.get('session_name')
            try:
                with open(SESSIONS_FILE, 'r') as f:
                    all_sessions = json.load(f)
                
                if session_name in all_sessions:
                    del all_sessions[session_name]
                    with open(SESSIONS_FILE, 'w') as f:
                        json.dump(all_sessions, f, indent=4)
                    return {"status": "success", "message": f"Session '{session_name}' deleted."}
                else:
                    return {"status": "error", "message": f"Session '{session_name}' not found."}
            except (FileNotFoundError, json.JSONDecodeError):
                 return {"status": "error", "message": "No sessions file found to delete from."}
        
        else:
            return {"status": "error", "message": "Unknown action"}
    except Exception as e:
        logging.error(f"Error executing tool command: {e}")
        return {"status": "error", "message": f"An error occurred: {e}"}