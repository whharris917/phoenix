import os
import io
import sys
from contextlib import redirect_stdout
import json
import logging
from eventlet import tpool
import chromadb
import uuid
from audit_logger import audit_log
from code_parser import analyze_codebase, generate_mermaid_diagram
import patcher
import debugpy
import builtins
from vertexai.generative_models import Content, Part

# --- Constants ---
CHROMA_DB_PATH = os.path.join(os.path.dirname(__file__), '.sandbox', 'chroma_db')

ALLOWED_PROJECT_FILES = [
    'public_data/system_prompt.txt',
    'app.py',
    'audit_logger.py',
    'audit_visualizer.py',
    'code_parser.py',
    'code_visualizer.py',
    'database_viewer.html',
    'documentation_viewer.html',
    'haven.py',
    'index.html',
    'inspect_db.py',
    'memory_manager.py',
    'orchestrator.py',
    'patcher.py',
    'requirements.txt',
    'tool_agent.py',
    'workshop.html'
]

# --- Helper functions (remain unchanged) ---
def _execute_script(script_content):
    string_io = io.StringIO()
    try:
        restricted_globals = {"__builtins__": {"print": print, "range": range, "len": len, "str": str, "int": int, "float": float, "list": list, "dict": dict, "set": set, "abs": abs, "max": max, "min": min, "sum": sum}}
        global_scope = {'__builtins__': builtins.__dict__}
        with redirect_stdout(string_io):
            exec(script_content, restricted_globals, {})
        return {"status": "success", "output": string_io.getvalue()}
    except Exception as e:
        return {"status": "error", "message": str(e)}

def _write_file(path, content):
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w', encoding='utf-8') as f:
            f.write(content)
        return {"status": "success"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

def _read_file(path):
    try:
        if not os.path.exists(path):
            return {"status": "error", "message": "File not found."}
        with open(path, 'r', encoding='utf-8') as f:
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
            if 'chroma_db' in dirs:
                dirs.remove('chroma_db')
            if 'sessions' in dirs:
                dirs.remove('sessions')

            for name in files:
                relative_path = os.path.relpath(os.path.join(root, name), path)
                file_list.append(relative_path.replace('\\\\', '/'))
        return {"status": "success", "files": file_list}
    except Exception as e:
        return {"status": "error", "message": str(e)}

def get_safe_path(filename, base_dir_name='sandbox'):
    base_dir = os.path.dirname(os.path.abspath(__file__))
    target_dir = os.path.join(base_dir, base_dir_name)
    if not os.path.exists(target_dir):
        os.makedirs(target_dir)
    
    requested_path = os.path.abspath(os.path.join(target_dir, filename))
    
    if not requested_path.startswith(target_dir):
        raise ValueError("Attempted path traversal outside of allowed directory.")
    return requested_path

# --- Core Tooling Logic (Modified for Haven) ---
def execute_tool_command(command, socketio, session_id, chat_sessions, haven_proxy, loop_id=None):
    action = command.get('action')
    params = command.get('parameters', {})
    try:
        chroma_client = chromadb.PersistentClient(path=CHROMA_DB_PATH)

        # --- File and System tools (mostly unchanged) ---
        if action == 'create_file':
            filename = params.get('filename', 'default.txt')
            content = params.get('content', '')
            safe_path = get_safe_path(filename)
            result = tpool.execute(_write_file, safe_path, content)
            return {"status": "success", "message": f"File '{filename}' created."} if result['status'] == 'success' else result
        
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
        
        # --- REFACTORED SESSION MANAGEMENT TOOLS (FOR HAVEN) ---

        elif action == 'load_session':
            from orchestrator import replay_history_for_client
            from memory_manager import MemoryManager

            session_name = params.get('session_name')
            if not session_name:
                return {"status": "error", "message": "Session name not provided."}

            try:
                # 1. Get history from DB to create/validate the session in Haven
                collection = chroma_client.get_collection(name=session_name)
                history_data = collection.get(include=["documents", "metadatas"])
                history_for_haven = []
                if history_data and history_data['ids']:
                     history_tuples = sorted(zip(history_data['documents'], history_data['metadatas']), key=lambda x: x[1].get('timestamp', 0))
                     for doc, meta in history_tuples:
                         history_for_haven.append({"role": meta.get('role', 'unknown'), "parts": [{"text": doc}]})

                # 2. Call Haven to get or create the live chat object
                haven_proxy.get_or_create_session(session_name, history_for_haven)

                # 3. Update the local session stub in app.py
                memory_manager = MemoryManager(session_name=session_name)
                chat_sessions[session_id] = {
                    "memory": memory_manager,
                    "name": session_name
                }
                
                socketio.emit('session_name_update', {'name': session_name}, to=session_id)
                
                # 4. Replay history for the client
                history_for_replay = history_for_haven[-memory_manager.max_buffer_size:]
                replay_history_for_client(socketio, session_id, session_name, history_for_replay)

                # 5. Update the session list on the client
                updated_list_result = execute_tool_command({'action': 'list_sessions'}, socketio, session_id, chat_sessions, haven_proxy)
                if updated_list_result.get('status') == 'success':
                    socketio.emit('session_list_update', updated_list_result, to=session_id)
                
                return {"status": "success", "message": f"Session '{session_name}' loaded and connected to Haven."}
            except Exception as e:
                logging.error(f"Error loading session '{session_name}': {e}")
                return {"status": "error", "message": f"Could not load session: {e}"}

        elif action == 'save_session':
            new_session_name = params.get('session_name')
            if not new_session_name:
                return {"status": "error", "message": "Session name not provided."}

            session_data = chat_sessions.get(session_id)
            if not session_data or 'memory' not in session_data:
                return {"status": "error", "message": "Active memory session not found."}
            
            memory = session_data['memory']
            source_collection_name = memory.session_name
            
            try:
                source_collection = chroma_client.get_collection(name=source_collection_name)
                history_to_copy = source_collection.get(include=["metadatas", "documents"])

                target_collection = chroma_client.create_collection(name=new_session_name)
                if history_to_copy and history_to_copy.get('ids'):
                    target_collection.add(
                        ids=history_to_copy['ids'],
                        documents=history_to_copy['documents'],
                        metadatas=history_to_copy['metadatas']
                    )
                
                # Update current session to point to the new name and collection
                memory.session_name = new_session_name
                memory.collection = target_collection
                session_data['name'] = new_session_name

                # Inform Haven to create a corresponding live object for this new session
                history_for_haven = []
                if history_to_copy and history_to_copy.get('ids'):
                     history_tuples = sorted(zip(history_to_copy['documents'], history_to_copy['metadatas']), key=lambda x: x[1].get('timestamp', 0))
                     for doc, meta in history_tuples:
                         history_for_haven.append({"role": meta.get('role', 'unknown'), "parts": [{"text": doc}]})
                haven_proxy.get_or_create_session(new_session_name, history_for_haven)

                socketio.emit('session_name_update', {'name': new_session_name}, to=session_id)
                return {"status": "success", "message": f"Session history saved as '{new_session_name}' and live session created in Haven."}

            except Exception as e:
                return {"status": "error", "message": f"Failed to save session history: {e}"}

        elif action == 'list_sessions':
            try:
                # Get saved sessions from DB
                db_collections = chroma_client.list_collections()
                db_sessions = {col.name: {"status": "Saved"} for col in db_collections if not col.name.startswith('New_Session_')}

                # Get live sessions from Haven
                live_session_names = haven_proxy.list_sessions()
                for name in live_session_names:
                    if name in db_sessions:
                        db_sessions[name]['status'] = "Live & Saved"
                    else:
                        db_sessions[name] = {"status": "Live"}

                session_list = [{'name': name, 'summary': data['status']} for name, data in db_sessions.items()]
                session_list.sort(key=lambda x: x['name'])

                return {"status": "success", "sessions": session_list}
            except Exception as e:
                logging.error(f"Failed to list sessions: {e}")
                return {"status": "error", "message": f"Failed to list sessions: {e}"}

        else:
            return {"status": "error", "message": f"Unknown action: {action}"}

    except Exception as e:
        logging.error(f"Error executing tool command: {e}")
        return {"status": "error", "message": f"An error occurred: {e}"}