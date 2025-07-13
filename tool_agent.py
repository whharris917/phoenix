# tool_agent.py

import os
import io
import sys
from contextlib import redirect_stdout
import json
import logging
from eventlet import tpool
import chromadb # Import chromadb at the top
import uuid

# --- MODIFIED: Import audit_log ---
from audit_logger import audit_log 
from code_parser import analyze_codebase, generate_mermaid_diagram

# --- Constants ---
LEGACY_SESSIONS_FILE = os.path.join(os.path.dirname(__file__), 'sandbox', 'sessions', 'sessions.json')
CHROMA_DB_PATH = os.path.join(os.path.dirname(__file__), '.sandbox', 'chroma_db') # Use the same path as MemoryManager

ALLOWED_PROJECT_FILES = [
    'app.py',
    'orchestrator.py',
    'tool_agent.py',
    'public_data/system_prompt.txt',
    'index.html',
    'workshop.html',
    'documentation_viewer.html',
    'code_parser.py'
]

# --- Helper functions ---
# ... (all helper functions like _execute_script, _write_file, etc. remain the same) ...
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
            # Exclude the chroma_db directory from the listing
            if 'chroma_db' in dirs:
                dirs.remove('chroma_db')
            if 'sessions' in dirs: # Also keep excluding old sessions dir
                dirs.remove('sessions')

            for name in files:
                relative_path = os.path.relpath(os.path.join(root, name), path)
                file_list.append(relative_path.replace('\\', '/'))
        return {"status": "success", "files": file_list}
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

# --- MODIFIED: Function signature now accepts socketio ---
def execute_tool_command(command, socketio, session_id, chat_sessions, model):
    action = command.get('action')
    params = command.get('parameters', {})
    try:
        # Initialize ChromaDB client for session tools
        chroma_client = chromadb.PersistentClient(path=CHROMA_DB_PATH)

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

        # --- REFACTORED AND MODIFIED SESSION MANAGEMENT TOOLS ---

        elif action == 'save_session':
            session_name = params.get('session_name')
            if not session_name:
                return {"status": "error", "message": "Session name not provided."}

            session_data = chat_sessions.get(session_id)
            if not session_data or 'memory' not in session_data:
                return {"status": "error", "message": "Active memory session not found."}
            
            old_session_name = session_data.get('name')
            memory = session_data['memory']
            current_collection = memory.collection
            if not current_collection:
                 return {"status": "error", "message": "ChromaDB collection not found for this session."}

            # Rename the current collection to the user-provided name
            current_collection.modify(name=session_name)
            
            # Update the memory manager to point to the renamed collection
            memory.collection = chroma_client.get_collection(name=session_name)
            
            # --- MODIFICATION START ---
            # 1. Update the name in the server's active session dictionary
            session_data['name'] = session_name

            # 2. Emit an event to the client to update the UI
            audit_log.log_event("Socket.IO Emit: session_name_update", session_id=session_id, session_name=session_name, source="Server", destination="Client", observers=["User", "Orchestrator"], details={'name': session_name, 'previous_name': old_session_name})
            socketio.emit('session_name_update', {'name': session_name}, to=session_id)
            # --- MODIFICATION END ---
            
            return {"status": "success", "message": f"Session '{session_name}' saved and session state updated."}

        elif action == 'list_sessions':
            collections = chroma_client.list_collections()
            # Filter out the temporary, session_id based collections
            named_sessions = [c.name for c in collections if not c.name.startswith('session_')]
            return {"status": "success", "sessions": [{"name": name, "summary": "Saved Session"} for name in named_sessions]}

        elif action == 'load_session':
            session_name = params.get('session_name')
            if not session_name:
                return {"status": "error", "message": "Session name not provided."}
                
            try:
                collection = chroma_client.get_collection(name=session_name)
                # Retrieve all documents and metadata
                history_data = collection.get(include=["documents", "metadatas"])
                
                if not history_data or not history_data['ids']:
                    return {"status": "success", "message": f"Session '{session_name}' loaded but is empty.", "history": []}

                # --- NEW: Sort by timestamp in metadata ---
                history_tuples = sorted(
                    zip(history_data['documents'], history_data['metadatas']), 
                    key=lambda x: x[1].get('timestamp', 0) # Sort by timestamp, default to 0 if missing
                )

                history = []
                for doc, meta in history_tuples:
                    # Reconstruct the chat history format
                    role = meta.get('role', 'unknown')
                    # The doc is "role: content", but we can just use the content part
                    # to avoid potential splitting errors if content contains ':'
                    content = doc.split(':', 1)[1] if ':' in doc else doc
                    history.append({"role": role, "parts": [{'text': content.strip()}]})

                # Re-initialize the chat session with the loaded history
                chat_sessions[session_id] = {
                    "chat": model.start_chat(history=history),
                    "memory": chat_sessions[session_id]['memory'], 
                    "name": session_name
                }
                # Update the memory manager's collection to the one we just loaded
                chat_sessions[session_id]['memory'].collection = collection
                chat_sessions[session_id]['memory'].conversational_buffer = history
                
                # --- MODIFICATION START ---
                # Emit an event to the client to update the UI with the new name
                audit_log.log_event("Socket.IO Emit: session_name_update", session_id=session_id, session_name=session_name, source="Server", destination="Client", observers=["User", "Orchestrator"], details={'name': session_name})
                socketio.emit('session_name_update', {'name': session_name}, to=session_id)
                # --- MODIFICATION END ---

                return {"status": "success", "message": f"Session '{session_name}' loaded.", "history": history}
            except ValueError:
                 return {"status": "error", "message": f"Session '{session_name}' not found."}
            except Exception as e:
                logging.error(f"Error loading session '{session_name}': {e}")
                return {"status": "error", "message": f"Could not load session: {e}"}
        
        elif action == 'delete_session':
            session_name = params.get('session_name')
            if not session_name:
                return {"status": "error", "message": "Session name not provided."}
            try:
                chroma_client.delete_collection(name=session_name)
                return {"status": "success", "message": f"Session '{session_name}' deleted."}
            except ValueError:
                 return {"status": "error", "message": f"Session '{session_name}' not found."}
            except Exception as e:
                logging.error(f"Error deleting session '{session_name}': {e}")
                return {"status": "error", "message": f"Could not delete session: {e}"}
        
        # --- NEW: Tool to import legacy sessions ---
        elif action == 'import_legacy_sessions':
            try:
                with open(LEGACY_SESSIONS_FILE, 'r') as f:
                    legacy_sessions = json.load(f)
            except (FileNotFoundError, json.JSONDecodeError):
                return {"status": "error", "message": "Legacy sessions.json file not found or is invalid."}

            imported_count = 0
            for session_name, data in legacy_sessions.items():
                try:
                    # Create a new collection for each legacy session
                    collection = chroma_client.get_or_create_collection(name=session_name)
                    
                    history = data.get('history', [])
                    docs_to_add = []
                    metadatas_to_add = []
                    ids_to_add = []

                    for turn in history:
                        role = turn.get('role')
                        content = turn.get('parts', [{}])[0].get('text', '')
                        if role and content:
                            docs_to_add.append(f"{role}: {content}")
                            metadatas_to_add.append({'role': role})
                            ids_to_add.append(str(uuid.uuid4()))
                    
                    if docs_to_add:
                        collection.add(
                            documents=docs_to_add,
                            metadatas=metadatas_to_add,
                            ids=ids_to_add
                        )
                    imported_count += 1
                except Exception as e:
                    logging.error(f"Could not import legacy session '{session_name}': {e}")
            
            return {"status": "success", "message": f"Successfully imported {imported_count} legacy sessions into ChromaDB."}

        else:
            return {"status": "error", "message": "Unknown action"}

    except Exception as e:
        logging.error(f"Error executing tool command: {e}")
        return {"status": "error", "message": f"An error occurred: {e}"}
