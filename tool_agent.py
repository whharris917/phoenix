"""
Provides the secure action execution layer for the AI agent.

This module acts as the "hands" of the agent, providing the exclusive and
secure interface through which the agent can interact with the local system.
It is designed around a declarative, strategy-based pattern: the orchestrator
issues a command, and this module dispatches it to the appropriate handler
via the TOOL_REGISTRY.

All file system operations are strictly confined to a sandboxed directory to
ensure safety. Every tool execution returns a standardized ToolResult object,
providing a consistent data contract for the orchestrator.
"""
import os
import io
import logging
from contextlib import redirect_stdout
from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional
from multiprocessing.managers import BaseManager

import chromadb
from eventlet import tpool

import patcher
from config import ALLOWED_PROJECT_FILES, CHROMA_DB_PATH
from data_models import ToolCommand, ToolResult
from memory_manager import ChromaDBStore, MemoryManager
from proxies import HavenProxyWrapper
from session_models import ActiveSession
from tracer import trace


# A data class to neatly pass context-dependent objects to tool handlers.
@dataclass
class ToolContext:
    """A container for passing stateful objects to tool handlers."""
    socketio: Any
    session_id: str
    chat_sessions: dict[str, ActiveSession]
    haven_proxy: BaseManager
    loop_id: Optional[str]

# --- Low-Level File System Helpers ---
@trace
def _execute_script(script_content: str) -> ToolResult:
    """Executes a Python script in a restricted environment and captures its output."""
    string_io = io.StringIO()
    try:
        # Define a highly restricted set of globals to prevent malicious code execution.
        restricted_globals = {
            "__builtins__": {
                "print": print, "range": range, "len": len, "str": str, "int": int,
                "float": float, "list": list, "dict": dict, "set": set, "abs": abs,
                "max": max, "min": min, "sum": sum,
            }
        }
        with redirect_stdout(string_io):
            exec(script_content, restricted_globals, {})
        return ToolResult(status="success", message="Script executed.", content=string_io.getvalue())
    except Exception as e:
        return ToolResult(status="error", message=str(e))

@trace
def _write_file(path: str, content: str) -> ToolResult:
    """Writes content to a file, creating directories if necessary."""
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        return ToolResult(status="success", message=f"File '{os.path.basename(path)}' written successfully.")
    except Exception as e:
        return ToolResult(status="error", message=str(e))

@trace
def _read_file(path: str) -> ToolResult:
    """Reads the content of a file."""
    try:
        if not os.path.exists(path):
            return ToolResult(status="error", message="File not found.")
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        return ToolResult(status="success", content=content, message=f"Read content from '{os.path.basename(path)}'.")
    except Exception as e:
        return ToolResult(status="error", message=str(e))

@trace
def _delete_file(path: str) -> ToolResult:
    """Deletes a file from the filesystem."""
    try:
        if not os.path.exists(path):
            return ToolResult(status="error", message="File not found.")
        os.remove(path)
        return ToolResult(status="success", message=f"File '{os.path.basename(path)}' deleted.")
    except Exception as e:
        return ToolResult(status="error", message=str(e))

@trace
def _list_directory(path: str) -> ToolResult:
    """Lists all files in a directory recursively, ignoring certain subdirectories."""
    try:
        file_list = []
        for root, dirs, files in os.walk(path):
            # Exclude specified directories from the walk.
            dirs[:] = [d for d in dirs if d not in ["chroma_db", "sessions", ".git", "__pycache__"]]
            for name in files:
                relative_path = os.path.relpath(os.path.join(root, name), path)
                file_list.append(relative_path.replace("\\", "/"))
        return ToolResult(status="success", content=file_list, message="Listed files in directory.")
    except Exception as e:
        return ToolResult(status="error", message=str(e))

@trace
def get_safe_path(filename: str, base_dir_name: str = "sandbox") -> str:
    """Constructs a safe file path within a designated directory, preventing path traversal."""
    base_dir = os.path.dirname(os.path.abspath(__file__))
    target_dir = os.path.join(base_dir, base_dir_name)
    os.makedirs(target_dir, exist_ok=True)
    # Get the absolute path of the requested file.
    requested_path = os.path.abspath(os.path.join(target_dir, filename))
    # Ensure the resolved path is still within the target directory.
    if not requested_path.startswith(target_dir):
        raise ValueError("Attempted path traversal outside of the allowed directory.")
    return requested_path

# --- Decomposed `apply_patch` Helpers ---
@trace
def _extract_patch_paths(diff_content: str) -> tuple[str | None, str | None]:
    """Extracts source (a) and target (b) filenames from a diff header."""
    source_filename, target_filename = None, None
    for line in diff_content.splitlines():
        if line.startswith("--- a/"):
            source_filename = line.split("--- a/")[1].strip()
        if line.startswith("+++ b/"):
            target_filename = line.split("+++ b/")[1].strip()
        if source_filename and target_filename:
            break
    return source_filename, target_filename

@trace
def _validate_patch_paths(source_filename: str, target_filename: str) -> ToolResult | None:
    """Validates the source and target paths for the patch."""
    if not target_filename.startswith("sandbox/"):
        return ToolResult(status="error", message="Target file path in diff header (+++ b/) must start with 'sandbox/'.")
    if not source_filename.startswith("sandbox/") and source_filename not in ALLOWED_PROJECT_FILES:
        return ToolResult(status="error", message=f"Access denied. Patching the project file '{source_filename}' is not permitted.")
    return None

@trace
def _get_source_read_path(source_filename: str) -> str:
    """Determines the absolute path from which to read the source file."""
    if source_filename.startswith("sandbox/"):
        relative_source_filename = source_filename[len("sandbox/") :]
        return get_safe_path(relative_source_filename)
    else:
        return os.path.join(os.path.dirname(__file__), source_filename)

# --- Modular Tool Handlers ---
@trace
def _handle_create_file(params: dict, context: ToolContext) -> ToolResult:
    """Handles the 'create_file' action."""
    filename = params.get("filename", "default.txt")
    content = params.get("content", "")
    safe_path = get_safe_path(filename)
    return tpool.execute(_write_file, safe_path, content)

@trace
def _handle_read_file(params: dict, context: ToolContext) -> ToolResult:
    """Handles the 'read_file' action."""
    filename = params.get("filename")
    if not filename:
        return ToolResult(status="error", message="Missing required parameter: filename.")
    safe_path = get_safe_path(filename)
    return tpool.execute(_read_file, safe_path)

@trace
def _handle_read_project_file(params: dict, context: ToolContext) -> ToolResult:
    """Handles the 'read_project_file' action with validation."""
    filename = params.get("filename")
    if not filename:
        return ToolResult(status="error", message="Missing required parameter: filename.")
    if filename not in ALLOWED_PROJECT_FILES:
        return ToolResult(status="error", message=f"Access denied. Reading the project file '{filename}' is not permitted.")
    project_file_path = os.path.join(os.path.dirname(__file__), filename)
    return tpool.execute(_read_file, project_file_path)

@trace
def _handle_list_allowed_project_files(params: dict, context: ToolContext) -> ToolResult:
    """Handles the 'list_allowed_project_files' action."""
    return ToolResult(status="success", message="Listed allowed project files.", content=ALLOWED_PROJECT_FILES)

@trace
def _handle_list_directory(params: dict, context: ToolContext) -> ToolResult:
    """Handles the 'list_directory' action."""
    # The path should be the sandbox directory itself.
    sandbox_dir = get_safe_path("")
    return tpool.execute(_list_directory, sandbox_dir)

@trace
def _handle_delete_file(params: dict, context: ToolContext) -> ToolResult:
    """Handles the 'delete_file' action."""
    filename = params.get("filename")
    if not filename:
        return ToolResult(status="error", message="Missing required parameter: filename.")
    safe_path = get_safe_path(filename)
    return tpool.execute(_delete_file, safe_path)

@trace
def _handle_execute_python_script(params: dict, context: ToolContext) -> ToolResult:
    """Handles the 'execute_python_script' action."""
    script_content = params.get("script_content", "")
    return tpool.execute(_execute_script, script_content)

@trace
def _handle_apply_patch(params: dict, context: ToolContext) -> ToolResult:
    """Orchestrates the 'apply_patch' action by calling decomposed helpers."""
    diff_filename = params.get("diff_filename")
    confirmed = params.get("confirmed", False)
    if not diff_filename:
        return ToolResult(status="error", message="Missing required parameter: diff_filename.")

    # Step 1: Read the content of the diff file.
    diff_path = get_safe_path(diff_filename)
    read_result = tpool.execute(_read_file, diff_path)
    if read_result.status == "error": return read_result
    diff_content = read_result.content

    # Step 2: Extract and validate paths from the diff header.
    source_filename, target_filename = _extract_patch_paths(diff_content)
    if not source_filename or not target_filename:
        return ToolResult(status="error", message="Could not determine source/target filename from diff header.")
    
    validation_error = _validate_patch_paths(source_filename, target_filename)
    if validation_error: return validation_error
    
    # Step 3: Get the safe path to save the target file and check for overwrites.
    relative_target_filename = target_filename[len("sandbox/") :]
    target_save_path = get_safe_path(relative_target_filename)
    if os.path.exists(target_save_path) and not confirmed:
        return ToolResult(status="error", message=f"File '{target_filename}' already exists. Must request user confirmation to overwrite.")

    # Step 4: Read the original content from the correct source location.
    source_read_path = _get_source_read_path(source_filename)
    read_result = tpool.execute(_read_file, source_read_path)
    if read_result.status == "error": return read_result
    original_content = read_result.content
    
    # Step 5: Apply the patch and write the new content.
    internal_diff_content = diff_content.replace(f"+++ b/{target_filename}", f"+++ b/{source_filename}")
    new_content, error_message = patcher.apply_patch(internal_diff_content, original_content, source_filename)
    if error_message: return ToolResult(status="error", message=error_message)
    
    write_result = tpool.execute(_write_file, target_save_path, new_content)
    if write_result.status == "error": return write_result
    
    return ToolResult(status="success", message=f"Patch applied successfully. File saved to '{target_filename}'.")

@trace
def _handle_list_sessions(params: dict, context: ToolContext) -> ToolResult:
    """Handles the 'list_sessions' action."""
    try:
        chroma_client = chromadb.PersistentClient(path=CHROMA_DB_PATH)
        db_collections = chroma_client.list_collections()
        db_sessions = {col.name: {"status": "Saved"} for col in db_collections if col.name.startswith("turns-")}
        
        live_session_names = context.haven_proxy.list_sessions()
        for name in live_session_names:
            saved_name = f"turns-{name}"
            if saved_name in db_sessions:
                db_sessions[saved_name]["status"] = "Live & Saved"
            else:
                db_sessions[name] = {"status": "Live"}

        session_list = [{"name": name.replace("turns-", ""), "summary": data["status"]} for name, data in db_sessions.items()]
        session_list.sort(key=lambda x: x["name"])
        return ToolResult(status="success", content=session_list, message="Retrieved all sessions.")
    except Exception as e:
        return ToolResult(status="error", message=f"Failed to list sessions: {e}")

@trace
def _handle_load_session(params: dict, context: ToolContext) -> ToolResult:
    """Handles the 'load_session' action."""
    from events import replay_history_for_client
    session_name = params.get("session_name")
    if not session_name:
        return ToolResult(status="error", message="Session name not provided.")
    try:
        turn_store: ChromaDBStore = ChromaDBStore(collection_name=f"turns-{session_name}")
        history_records = turn_store.get_all_records()
        history_for_haven = [{"role": r.role, "parts": [{"text": r.document}]} for r in history_records if r.role]

        chat_wrapper = HavenProxyWrapper(context.haven_proxy, session_name)
        memory_manager = MemoryManager(session_name=session_name)
        history_slice_for_haven = history_for_haven[-memory_manager.max_buffer_size :]
        context.haven_proxy.get_or_create_session(session_name, history_slice_for_haven)

        context.chat_sessions[context.session_id] = ActiveSession(chat=chat_wrapper, memory=memory_manager, name=session_name)
        context.socketio.emit("session_name_update", {"name": session_name}, to=context.session_id)
        replay_history_for_client(context.socketio, context.session_id, session_name, history_slice_for_haven)
        return ToolResult(status="success", message=f"Session '{session_name}' loaded.")
    except Exception as e:
        return ToolResult(status="error", message=f"Could not load session: {e}")

@trace
def _handle_save_session(params: dict, context: ToolContext) -> ToolResult:
    """Handles the 'save_session' action."""
    new_session_name = params.get("session_name")
    if not new_session_name:
        return ToolResult(status="error", message="Session name not provided.")
    session_data = context.chat_sessions.get(context.session_id)
    if not session_data:
        return ToolResult(status="error", message="Active session not found.")
    try:
        source_turn_store: ChromaDBStore = session_data.memory.turn_store
        target_turn_store: ChromaDBStore = ChromaDBStore(collection_name=f"turns-{new_session_name}")
        records_to_copy = source_turn_store.get_all_records()
        for record in records_to_copy:
            target_turn_store.add_record(record, str(record.id))

        source_code_store: ChromaDBStore = session_data.memory.code_store
        target_code_store: ChromaDBStore = ChromaDBStore(collection_name=f"code-{new_session_name}")
        code_records_to_copy = source_code_store.get_all_records()
        for record in code_records_to_copy:
            pointer_id = f"[CODE-ARTIFACT-{record.id}:{record.filename}]"
            target_code_store.add_record(record, pointer_id)

        session_data.memory.session_name = new_session_name
        session_data.memory.turn_store = target_turn_store
        session_data.memory.code_store = target_code_store
        session_data.name = new_session_name
        session_data.chat = HavenProxyWrapper(context.haven_proxy, new_session_name)

        history_for_haven = [{"role": r.role, "parts": [{"text": r.document}]} for r in records_to_copy if r.role]
        context.haven_proxy.get_or_create_session(new_session_name, history_for_haven)
        context.socketio.emit("session_name_update", {"name": new_session_name}, to=context.session_id)
        return ToolResult(status="success", message=f"Session saved as '{new_session_name}'.")
    except Exception as e:
        return ToolResult(status="error", message=f"Failed to save session: {e}")

@trace
def _handle_delete_session(params: dict, context: ToolContext) -> ToolResult:
    """Handles the 'delete_session' action."""
    session_name = params.get("session_name")
    if not session_name:
        return ToolResult(status="error", message="Session name not provided.")
    try:
        turn_store = ChromaDBStore(collection_name=f"turns-{session_name}")
        code_store = ChromaDBStore(collection_name=f"code-{session_name}")
        turn_store.delete_collection()
        code_store.delete_collection()
        context.haven_proxy.delete_session(session_name)
        
        updated_list_result = _handle_list_sessions({}, context)
        context.socketio.emit("session_list_update", updated_list_result.model_dump(), to=context.session_id)
        return ToolResult(status="success", message=f"Session '{session_name}' deleted from both database and Haven.")
    except Exception as e:
        logging.error(f"Error deleting session '{session_name}': {e}")
        return ToolResult(status="error", message=f"Could not delete session: {e}")

# --- Tool Registry (Strategy Pattern) ---
# A dictionary mapping action names to their handler functions. This is the core
# of the declarative, strategy-based design of the tool agent.
TOOL_REGISTRY: Dict[str, Callable[[Dict, ToolContext], ToolResult]] = {
    "create_file": _handle_create_file,
    "read_file": _handle_read_file,
    "read_project_file": _handle_read_project_file,
    "list_allowed_project_files": _handle_list_allowed_project_files,
    "list_directory": _handle_list_directory,
    "delete_file": _handle_delete_file,
    "execute_python_script": _handle_execute_python_script,
    "apply_patch": _handle_apply_patch,
    "list_sessions": _handle_list_sessions,
    "load_session": _handle_load_session,
    "save_session": _handle_save_session,
    "delete_session": _handle_delete_session,
}

# --- Core Execution Logic ---
@trace
def execute_tool_command(
    command: ToolCommand,
    socketio,
    session_id: str,
    chat_sessions: dict[str, ActiveSession],
    haven_proxy: BaseManager,
    loop_id: str | None = None,
) -> ToolResult:
    """
    Executes a tool command by dispatching to the appropriate handler.
    This function is the single entry point for all tool executions. It uses a
    strategy pattern (TOOL_REGISTRY) to delegate the work to modular handlers.
    """
    action = command.action
    params = command.parameters
    
    handler = TOOL_REGISTRY.get(action)
    
    if not handler:
        return ToolResult(status="error", message=f"Unknown action: {action}")
        
    try:
        # Create a context object to pass necessary state to the handlers.
        context = ToolContext(
            socketio=socketio,
            session_id=session_id,
            chat_sessions=chat_sessions,
            haven_proxy=haven_proxy,
            loop_id=loop_id
        )
        # Call the appropriate handler with its parameters and context.
        return handler(params, context)
        
    except Exception as e:
        logging.error(f"Error in execute_tool_command dispatch for action '{action}': {e}", exc_info=True)
        return ToolResult(status="error", message=f"An internal error occurred during tool execution: {e}")
