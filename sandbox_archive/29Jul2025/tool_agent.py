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
LEGACY_SESSIONS_FILE = os.path.join(os.path.dirname(__file__), 'sandbox', 'sessions', 'sessions.json')
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

# --- Helper functions ---

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

def execute_tool_command(command, socketio, session_id, chat_sessions, model, loop_id=None):
    action = command.get('action')
    params = command.get('parameters', {})
    try:
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

        elif action == 'apply_patch':
            diff_filename = params.get('diff_filename')
            confirmed = params.get('confirmed', False)

            if not diff_filename:
                return {"status": "error", "message": "Missing required parameter: diff_filename."}

            diff_path = get_safe_path(diff_filename)
            diff_result = tpool.execute(_read_file, diff_path)
            if diff_result['status'] == 'error':
                return diff_result
            diff_content = diff_result['content']

            # 1. Extract source (a) and target (b) filenames from diff header
            source_filename = None
            target_filename = None
            for line in diff_content.splitlines():
                if line.startswith('--- a/'):
                    source_filename = line.split('--- a/')[1].strip()
                if line.startswith('+++ b/'):
                    target_filename = line.split('+++ b/')[1].strip()
                if source_filename and target_filename:
                    break
            
            if not source_filename or not target_filename:
                return {"status": "error", "message": "Could not determine source and/or target filename from diff header."}

            # 2. Validate that the target path must be in the sandbox
            if not target_filename.startswith('sandbox/'):
                return {"status": "error", "message": "Target file path in diff header (+++ b/) must start with 'sandbox/'."}
            
            # Strip the 'sandbox/' prefix to use get_safe_path correctly
            relative_target_filename = target_filename[len('sandbox/'):]
            
            try:
                target_save_path = get_safe_path(relative_target_filename)
            except ValueError as e:
                return {"status": "error", "message": str(e)}

            # 3. Handle overwrite confirmation
            if os.path.exists(target_save_path) and not confirmed:
                return {
                    "status": "error",
                    "message": f"File '{target_filename}' already exists. To overwrite, add '\"confirmed\": true' to the parameters of the 'apply_patch' action."
                }

            # 4. Determine the absolute path to read the source file from
            source_read_path = None
            if source_filename.startswith('sandbox/'):
                relative_source_filename = source_filename[len('sandbox/'):]
                try:
                    source_read_path = get_safe_path(relative_source_filename)
                except ValueError as e:
                    return {"status": "error", "message": f"Invalid source path in diff: {e}"}
            else:
                # If not in sandbox, it must be an allowed project file
                if source_filename not in ALLOWED_PROJECT_FILES:
                    return {"status": "error", "message": f"Access denied. Patching the project file '{source_filename}' is not permitted."}
                source_read_path = os.path.join(os.path.dirname(__file__), source_filename)

            # 5. Read original content from the determined source path
            read_result = tpool.execute(_read_file, source_read_path)
            if read_result['status'] == 'error':
                return read_result
            original_content = read_result['content']

            # 6. Create a temporary, in-memory version of the diff content where the
            # target path matches the source path. This is required for the patch
            # utility to work correctly in its isolated temporary directory.
            internal_diff_content = diff_content.replace(f"+++ b/{target_filename}", f"+++ b/{source_filename}")

            # 7. Apply the patch using the patcher utility with the modified diff
            new_content, error_message = patcher.apply_patch(internal_diff_content, original_content, source_filename)
            
            if error_message:
                return {"status": "error", "message": error_message}

            # 8. Write the new, patched content to the validated target path
            write_result = tpool.execute(_write_file, target_save_path, new_content)
            if write_result['status'] == 'error':
                return write_result

            return {"status": "success", "message": f"Patch applied successfully. File saved to '{target_filename}'."}

        # --- REFACTORED AND MODIFIED SESSION MANAGEMENT TOOLS ---
        elif action == 'save_session': # Implements 'Save As' functionality
            new_session_name = params.get('session_name')
            if not new_session_name:
                return {"status": "error", "message": "Session name not provided."}

            session_data = chat_sessions.get(session_id)
            if not session_data or 'memory' not in session_data:
                return {"status": "error", "message": "Active memory session not found."}
            
            memory = session_data['memory']
            source_collection = memory.collection
            source_session_name = memory.session_name

            if new_session_name == source_session_name:
                return {"status": "error", "message": "Cannot save session with the same name. Please provide a new name."}

            # Check if a session with the new name already exists to prevent overwriting.
            existing_collections = chroma_client.list_collections()
            existing_names = [col.name for col in existing_collections]
            if new_session_name in existing_names:
                return {"status": "error", "message": f"A session named '{new_session_name}' already exists. Please choose a different name."}

            # 1. Create the new collection
            try:
                target_collection = chroma_client.create_collection(name=new_session_name)
            except Exception as e:
                return {"status": "error", "message": f"Failed to create new session collection: {e}"}

            # 2. Copy history from the source collection to the new one
            history_to_copy = source_collection.get(include=["metadatas", "documents", "ids"])
            if history_to_copy and history_to_copy.get('ids'):
                target_collection.add(
                    ids=history_to_copy['ids'],
                    documents=history_to_copy['documents'],
                    metadatas=history_to_copy['metadatas']
                )

            # 3. Update the current session in memory to point to the new collection
            memory.collection = target_collection
            memory.session_name = new_session_name
            session_data['name'] = new_session_name

            # 4. Notify the client UI of the name change
            socketio.emit('session_name_update', {'name': new_session_name}, to=session_id)

            # 5. Log the event
            audit_log.log_event(
                event="Session Saved As",
                session_id=session_id, session_name=new_session_name, loop_id=loop_id,
                source="System", destination="Database",
                details=f"Copied from '{source_session_name}' to '{new_session_name}'. Active session is now '{new_session_name}'."
            )

            return {"status": "success", "message": f"Session saved as '{new_session_name}'. The original session '{source_session_name}' remains unchanged."}

        elif action == 'list_sessions':
            collections = chroma_client.list_collections()
            
            session_list = []
            for col in collections:
                if col.name.startswith('New_Session_'):
                    continue

                last_modified = 0
                metadata = col.get(include=["metadatas"]).get('metadatas')
                if metadata:
                    timestamps = [m.get('timestamp', 0) for m in metadata if m]
                    if timestamps:
                        last_modified = max(timestamps)
                
                session_list.append({
                    'name': col.name,
                    'last_modified': last_modified,
                    'summary': "Saved Session"
                })

            session_list.sort(key=lambda x: x['last_modified'], reverse=True)

            return {"status": "success", "sessions": session_list}

        elif action == 'load_session':
            from orchestrator import replay_history_for_client
            from memory_manager import MemoryManager # Import MemoryManager

            session_name = params.get('session_name')
            if not session_name:
                return {"status": "error", "message": "Session name not provided."}

            current_session_data = chat_sessions.get(session_id)
            if current_session_data:
                current_session_name = current_session_data.get('name')
                """
                if current_session_name and current_session_name.startswith("New_Session_"):
                    try:
                        memory_to_clear = current_session_data.get('memory')
                        if memory_to_clear:
                            logging.info(f"Auto-deleting unsaved collection '{current_session_name}' before loading new session.")
                            memory_to_clear.clear()
                            audit_log.log_event("DB Collection Deleted", session_id=session_id, session_name=current_session_name, source="System", destination="Database", details=f"Unsaved session '{current_session_name}' cleaned up.")
                    except Exception as e:
                        logging.error(f"Error during auto-cleanup: {e}")
                """

            try:
                collection = chroma_client.get_collection(name=session_name)
                history_data = collection.get(include=["documents", "metadatas"])
                
                # --- MODIFIED: full_history is now a list of Content objects ---
                full_history = []
                if history_data and history_data['ids']:
                    history_tuples = sorted(
                        zip(history_data['documents'], history_data['metadatas']), 
                        key=lambda x: x[1].get('timestamp', 0)
                    )
                    for doc, meta in history_tuples:
                        role = meta.get('role', 'unknown')
                        content = doc
                        
                        if role == 'user' and doc.startswith('user: '):
                            content = doc[len('user: '):]
                        elif role == 'model' and doc.startswith('model: '):
                            content = doc[len('model: '):]

                        # Create Content objects directly
                        full_history.append(Content(role=role, parts=[Part.from_text(content.strip())]))

                memory_manager = chat_sessions[session_id]['memory']
                memory_manager.collection = collection
                memory_manager.conversational_buffer = full_history # Now assigning a list of Content objects
                memory_manager.session_name = session_name
                
                # model.start_chat now receives the correct object type
                chat_sessions[session_id]['chat'] = model.start_chat(history=full_history)
                chat_sessions[session_id]['name'] = session_name
                
                socketio.emit('session_name_update', {'name': session_name}, to=session_id)

                # --- MODIFIED: Convert history back to dicts for client-side replay ---
                history_for_replay = full_history[-memory_manager.max_buffer_size:]

                # The replay_history_for_client function expects dicts, so we convert them back
                history_for_replay_dicts = [
                    {"role": c.role, "parts": [{"text": c.parts[0].text}]} for c in history_for_replay
                ]
                replay_history_for_client(socketio, session_id, session_name, history_for_replay_dicts)

                updated_list_result = execute_tool_command({'action': 'list_sessions'}, socketio, session_id, chat_sessions, model)
                if updated_list_result.get('status') == 'success':
                    socketio.emit('session_list_update', updated_list_result, to=session_id)
                
                return {"status": "success", "message": f"Session '{session_name}' loaded."}
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
                updated_list_result = execute_tool_command({'action': 'list_sessions'}, socketio, session_id, chat_sessions, model)
                if updated_list_result.get('status') == 'success':
                    socketio.emit('session_list_update', updated_list_result, to=session_id)

                return {"status": "success", "message": f"Session '{session_name}' deleted."}
            except ValueError:
                 return {"status": "error", "message": f"Session '{session_name}' not found."}
            except Exception as e:
                logging.error(f"Error deleting session '{session_name}': {e}")
                return {"status": "error", "message": f"Could not delete session: {e}"}
        
        elif action == 'import_legacy_sessions':
            try:
                with open(LEGACY_SESSIONS_FILE, 'r') as f:
                    legacy_sessions = json.load(f)
            except (FileNotFoundError, json.JSONDecodeError):
                return {"status": "error", "message": "Legacy sessions.json file not found or is invalid."}

            imported_count = 0
            for session_name, data in legacy_sessions.items():
                try:
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
