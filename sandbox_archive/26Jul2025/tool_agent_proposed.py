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

# --- Constants ---
LEGACY_SESSIONS_FILE = os.path.join(os.path.dirname(__file__), 'sandbox', 'sessions', 'sessions.json')
CHROMA_DB_PATH = os.path.join(os.path.dirname(__file__), '.sandbox', 'chroma_db') 

ALLOWED_PROJECT_FILES = [
'public_data/system_prompt.txt', 
    'api_usage.py',
    'app.py',
    'audit_logger.py',
    'audit_visualizer.py',
    'code_parser.py',
    'code_visualizer.py',
    'database_viewer.html',
    'documentation_viewer.html',
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
                file_list.append(relative_path.replace('\\\\', '/'))
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
                return {"status": "success", "message": f"Read content from '{filename}'.\", \"content\": result['content']"}
            else:
                return {"status": "error", "message": result['message']}
        
        elif action == 'read_project_file':
            filename = params.get('filename')
            if filename not in ALLOWED_PROJECT_FILES:
                return {"status": "error", "message": f"Access denied. Reading the project file '{filename}' is not permitted."}
            project_file_path = os.path.join(os.path.dirname(__file__), filename)
            result = tpool.execute(_read_file, project_file_path)
            if result['status'] == 'success':
                return {"status": "success", "message": f"Read content from project file '{filename}'.\", \"content\": result['content']"}
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
                return {"status": "error", "message": "Could not determine source or target filename from diff header."}

            if not target_filename.startswith('sandbox/'):
                return {"status": "error", "message": "Target file path in diff header (+++ b/) must start with 'sandbox/'."}
            
            relative_target_filename = target_filename[len('sandbox/'):]
            
            try:
                target_save_path = get_safe_path(relative_target_filename)
            except ValueError as e:
                return {"status": "error", "message": str(e)}

            if os.path.exists(target_save_path) and not confirmed:
                return {
                    "status": "error",
                    "message": f"File '{target_filename}' already exists. To overwrite, add '\\\"confirmed\\\": true' to the parameters of the 'apply_patch' action."
                }

            source_read_path = None
            if source_filename.startswith('sandbox/'):
                relative_source_filename = source_filename[len('sandbox/'):]
                try:
                    source_read_path = get_safe_path(relative_source_filename)
                except ValueError as e:
                    return {"status": "error", "message": f"Invalid source path in diff: {e}"}
            else:
                if source_filename not in ALLOWED_PROJECT_FILES:
                    return {"status": "error", "message": f"Access denied. Patching the project file '{source_filename}' is not permitted."}
                source_read_path = os.path.join(os.path.dirname(__file__), source_filename)

            read_result = tpool.execute(_read_file, source_read_path)
            if read_result['status'] == 'error':
                return read_result
            original_content = read_result['content']

            new_content, error_message = patcher.apply_patch(diff_content, original_content, source_filename)
            
            if error_message:
                return {"status": "error", "message": f"Failed to apply patch: {error_message}"}

            write_result = tpool.execute(_write_file, target_save_path, new_content)
            if write_result['status'] == 'error':
                return write_result

            return {"status": "success", "message": f"Patch applied successfully. File saved to '{target_filename}'."}

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

            current_collection.modify(name=session_name)
            memory.collection = chroma_client.get_collection(name=session_name)
            session_data['name'] = session_name

            audit_log.log_event(
                event="Socket.IO Emit: session_name_update",
                session_id=session_id, session_name=session_name, loop_id=loop_id,
                source="Server", destination="Client",
                details={'name': session_name, 'previous_name': old_session_name}
            )
            socketio.emit('session_name_update', {'name': session_name}, to=session_id)

            return {"status": "success", "message": f"Session '{session_name}' saved and session state updated."}

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
            from memory_manager import MemoryManager

            session_name = params.get('session_name')
            if not session_name:
                return {"status": "error", "message": "Session name not provided."}

            current_session_data = chat_sessions.get(session_id)
            if current_session_data:
                current_session_name = current_session_data.get('name')
                if current_session_name and current_session_name.startswith("New_Session_"):
                    try:
                        memory_to_clear = current_session_data.get('memory')
                        if memory_to_clear:
                            logging.info(f"Auto-deleting unsaved collection '{current_session_name}' before loading new session.")
                            memory_to_clear.clear()
                            audit_log.log_event("DB Collection Deleted", session_id=session_id, session_name=current_session_name, source="System", destination="Database", details=f"Unsaved session '{current_session_name}' cleaned up.")
                    except Exception as e:
                        logging.error(f"Error during auto-cleanup: {e}")

            try:
                memory_manager = MemoryManager(session_name=session_name)
                full_history = memory_manager.get_full_history()
                
                chat_sessions[session_id]['memory'] = memory_manager
                chat_sessions[session_id]['chat'] = model.start_chat(history=full_history)
                chat_sessions[session_id]['name'] = session_name
                
                socketio.emit('session_name_update', {'name': session_name}, to=session_id)
                
                replay_history_for_client(socketio, session_id, session_name, full_history)

                updated_list_result = execute_tool_command({'action': 'list_sessions'}, socketio, session_id, chat_sessions, model)
                if updated_list_result.get('status') == 'success':
                    socketio.emit('session_list_update', updated_list_result, to=session_id)
                
                # --- NEW: Trigger auto-summarization in the background ---
                socketio.emit('tool_log', {'data': "[Auto-summarization started in background...]"}, to=session_id)
                from orchestrator import execute_reasoning_loop
                summarize_prompt = "summarize this session"
                socketio.start_background_task(execute_reasoning_loop, socketio, chat_sessions[session_id], summarize_prompt, session_id, chat_sessions, model, {})


                return {"status": "success", "message": f"Session '{session_name}' loaded."}
            except ValueError as ve:
                 return {"status": "error", "message": f"Session '{session_name}' not found: {ve}"}
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
                            docs_to_add.append(content)
                            metadatas_to_add.append({'role': role, 'timestamp': time.time()})
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
        
        elif action == 'summarize_session':
            session_data = chat_sessions.get(session_id)
            if not session_data or 'memory' not in session_data:
                return {"status": "error", "message": "Active memory session not found for summarization."}
            
            memory = session_data['memory']
            all_turns = memory.get_all_turns()
            
            turns_to_summarize = [
                turn for turn in all_turns 
                if 'turn_summary' not in turn.get('metadata', {})
            ]

            if not turns_to_summarize:
                return {"status": "success", "message": "All turns in the session have already been summarized."}

            # This is a simplified representation of the prompt.
            # In a real scenario, this would be a more complex, structured prompt.
            prompt = "Please summarize the following turns and group them into segments:\n\n"
            for turn in turns_to_summarize:
                prompt += f"- ID: {turn['id']}\\n- Role: {turn['metadata'].get('role', 'unknown')}\\n- Content: {turn['document']}\\n\\n"
            
            prompt += "\\nReturn a JSON object with a list of 'summaries', where each item has 'id', 'turn_summary', 'segment_id', and 'segment_summary'."

            # In a real implementation, you would send this to the model
            # and get a structured JSON response back.
            # For this example, we'll simulate a response.
            
            # --- SIMULATED MODEL RESPONSE ---
            simulated_response_data = {
                "summaries": [
                    {
                        "id": turn['id'],
                        "turn_summary": f"This is a summary for turn {i}.",
                        "segment_id": f"segment_{i//5}",
                        "segment_summary": f"This is a summary for segment {i//5}."
                    } for i, turn in enumerate(turns_to_summarize)
                ]
            }
            # --- END SIMULATION ---
            
            ids_to_update = []
            metadatas_to_update = []
            
            # Find the original metadata and update it
            all_turns_dict = {turn['id']: turn for turn in all_turns}
            
            for summary_item in simulated_response_data['summaries']:
                turn_id = summary_item['id']
                if turn_id in all_turns_dict:
                    original_turn = all_turns_dict[turn_id]
                    updated_metadata = original_turn['metadata'].copy()
                    updated_metadata['turn_summary'] = summary_item['turn_summary']
                    updated_metadata['segment_id'] = summary_item['segment_id']
                    updated_metadata['segment_summary'] = summary_item['segment_summary']
                    
                    ids_to_update.append(turn_id)
                    metadatas_to_update.append(updated_metadata)

            if ids_to_update:
                memory.update_turns_metadata(ids_to_update, metadatas_to_update)

            return {"status": "success", "message": f"Summarized {len(turns_to_summarize)} new turns."}


        else:
            return {"status": "error", "message": "Unknown action"}

    except Exception as e:
        logging.error(f"Error executing tool command: {e}")
        return {"status": "error", "message": f"An error occurred: {e}"}