"""
Handles all SocketIO event logic for the application.

This module centralizes the real-time communication between the client (UI)
and the server, managing user sessions, tasks, and other client requests.
It is designed to be registered by the main app.py script.
"""

import logging
from flask import request
from flask_socketio import SocketIO
import json

from audit_logger import audit_log
import inspect_db as db_inspector
from data_models import ToolCommand, ToolResult
from session_models import ActiveSession
from memory_manager import MemoryManager
from orchestrator import execute_reasoning_loop, confirmation_events
from proxies import HavenProxyWrapper
from tool_agent import execute_tool_command
from utils import get_timestamp
from response_parser import parse_agent_response, _handle_payloads
from tracer import trace, global_tracer

# --- Module-level state ---
# These dictionaries hold the state for all active user connections.
chat_sessions: dict[str, ActiveSession] = {}
# A reference to the haven_proxy object initialized in app.py
_haven_proxy = None

@trace
def replay_history_for_client(socketio, session_id, session_name, history):
    """
    Parses raw chat history and emits granular rendering events to the client.
    This allows a saved session to be loaded and displayed correctly.
    """
    try:
        socketio.emit("clear_chat_history", to=session_id)
        socketio.sleep(0.1)
        for item in history:
            role = item.get("role")
            raw_text = (item.get("parts", [{}])[0] or {}).get("text", "")
            if not raw_text or not raw_text.strip():
                continue
            if role == "user":
                is_tool_result = False
                # Handle different formats for tool results that might be in history.
                if raw_text.startswith(("TOOL_RESULT:", "OBSERVATION:", "Tool Result:")):
                    try:
                        tool_result = ToolResult.model_validate(json.loads(raw_text[raw_text.find("{") :]))
                        socketio.emit("tool_log", {"data": f"[{tool_result.message}]"}, to=session_id)
                        is_tool_result = True
                    except (json.JSONDecodeError, IndexError):
                        socketio.emit("tool_log", {"data": f"[{raw_text}]"}, to=session_id)
                        is_tool_result = True
                if not is_tool_result:
                    try:
                        tool_result_dict = json.loads(raw_text)
                        if isinstance(tool_result_dict, dict) and "status" in tool_result_dict:
                            tool_result = ToolResult.model_validate(tool_result_dict)
                            socketio.emit("tool_log", {"data": f"[{tool_result.message}]"}, to=session_id)
                            is_tool_result = True
                    except (json.JSONDecodeError, TypeError):
                        pass # Not a pure JSON object, treat as a regular message.
                if is_tool_result:
                    continue
                if not raw_text.startswith("USER_CONFIRMATION:"):
                    socketio.emit("log_message", {"type": "user", "data": raw_text}, to=session_id)
            elif role == "model":
                # Use the consistent ParsedAgentResponse object.
                parsed = parse_agent_response(raw_text)
                if parsed.is_prose_empty:
                    continue
                cleaned_prose, _ = _handle_payloads(parsed.prose, parsed.command)
                final_message = ""
                # Determine what to display based on the command and cleaned prose.
                if parsed.command and parsed.command.action in ["respond", "task_complete"]:
                    response_param = parsed.command.parameters.get("response", "")
                    final_message = response_param if len(response_param) > len(cleaned_prose or "") else cleaned_prose
                elif cleaned_prose:
                    final_message = cleaned_prose
                # Render the messages based on the processed data.
                if final_message:
                    socketio.emit("log_message", {"type": "final_answer", "data": final_message}, to=session_id)
                elif cleaned_prose: # This handles cases where prose is an intro to a command.
                    socketio.emit("log_message", {"type": "info", "data": cleaned_prose}, to=session_id)
                if parsed.command and parsed.command.action == "request_confirmation":
                    prompt = parsed.command.parameters.get("prompt", "Are you sure?")
                    socketio.emit("log_message", {"type": "system_confirm_replayed", "data": prompt}, to=session_id)
            socketio.sleep(0.01)
    except Exception as e:
        logging.error(f"Error during history replay for session {session_name}: {e}")
        socketio.emit("log_message", {"type": "error", "data": f"Failed to replay history: {e}"}, to=session_id)

@trace
def _create_new_session(session_id: str, proxy: object) -> ActiveSession:
    """
    Creates a new user session and initializes all necessary components.

    This involves creating a session in the Haven service, initializing the
    memory manager, and wrapping them in a structured ActiveSession object.

    Args:
        session_id: The unique SocketIO session identifier.
        proxy: The proxy object for the Haven service.

    Returns:
        An initialized ActiveSession object.
    """
    new_session_name = f"New_Session_{get_timestamp()}"
    logging.info(f"Creating new session '{new_session_name}' for client {session_id}.")
    
    # Create a live session in the Haven service to hold the model's chat history.
    proxy.get_or_create_session(new_session_name, [])
    logging.info(f"Live session '{new_session_name}' created or confirmed in Haven.")

    # Construct the local ActiveSession object that holds the session's state.
    session_data = ActiveSession(
        chat=HavenProxyWrapper(proxy, new_session_name),
        memory=MemoryManager(session_name=new_session_name),
        name=new_session_name,
    )
    return session_data

@trace
def register_events(socketio: SocketIO, haven_proxy: object):
    """
    Registers all SocketIO event handlers with the main application.

    This function acts as the entry point for this module, setting up the
    global haven_proxy reference and connecting the event handlers.
    """
    global _haven_proxy
    _haven_proxy = haven_proxy

    @socketio.on("connect")
    @trace
    def handle_connect(auth=None) -> None:
        """
        Handles a new client connection by creating and initializing a new session.
        """
        session_id = request.sid
        logging.info(f"Client connected: {session_id}")

        if not _haven_proxy:
            socketio.emit("log_message", {"type": "error", "data": "Haven service not available."}, to=session_id)
            return

        try:
            session_data = _create_new_session(session_id, _haven_proxy)
            chat_sessions[session_id] = session_data
            logging.info(f"Local session stub created for {session_id} with name {session_data.name}.")

            # Send initial state information to the newly connected client.
            socketio.emit("session_name_update", {"name": session_data.name}, to=session_id)
            socketio.emit("session_config_update", {"max_buffer_size": session_data.memory.max_buffer_size}, to=session_id)

        except Exception as e:
            logging.exception(f"Could not create session for {session_id}: {e}")
            socketio.emit("log_message", {"type": "error", "data": "Failed to initialize session."}, to=session_id)

    @socketio.on("disconnect")
    @trace
    def handle_disconnect(auth=None) -> None:
        """Handles client disconnection by cleaning up session data."""
        session_id = request.sid
        if session_id in chat_sessions:
            session_name = chat_sessions[session_id].name
            logging.info(f"Client disconnected: {session_id}, Session: {session_name}")
            # Clean up the session state to prevent memory leaks.
            chat_sessions.pop(session_id, None)
            confirmation_events.pop(session_id, None)

    @socketio.on("start_task")
    @trace
    def handle_start_task(data: dict) -> None:
        """
        Receives a task from the client and starts the agent's reasoning loop.
        
        Args:
            data: A dictionary of the form {"prompt": "This is the content of the prompt."}   
        """
        session_id = request.sid
        session_data = chat_sessions.get(session_id)
        if not session_data:
            socketio.emit("log_message", {"type": "error", "data": "No active session. Please refresh."}, to=session_id)
            return

        prompt = data.get("prompt")
        if prompt:
            timestamped_prompt = f"[{get_timestamp()}] {prompt}"
            socketio.emit("display_user_prompt", {"prompt": timestamped_prompt}, to=session_id)
            # Start the main agent logic in a background task to keep the server responsive.
            socketio.start_background_task(
                execute_reasoning_loop,
                socketio, session_data, timestamped_prompt,
                session_id, chat_sessions, _haven_proxy,
            )

    @socketio.on("request_session_list")
    @trace
    def handle_session_list_request(auth=None) -> None:
        """Handles a client's request for the list of available sessions."""
        session_id = request.sid
        # The 'list_sessions' tool provides a unified view of live and saved sessions.
        tool_result = execute_tool_command(
            ToolCommand(action="list_sessions"),
            socketio, session_id, chat_sessions, _haven_proxy
        )
        socketio.emit("session_list_update", tool_result.model_dump(), to=session_id)

    @socketio.on("request_session_name")
    @trace
    def handle_session_name_request(auth=None) -> None:
        """Handles a client's request for its current session name."""
        session_id = request.sid
        if session_data := chat_sessions.get(session_id):
            socketio.emit("session_name_update", {"name": session_data.name}, to=session_id)

    @socketio.on("request_db_collections")
    @trace
    def handle_db_collections_request(auth=None) -> None:
        """Forwards a request for DB collections to the db_inspector."""
        session_id = request.sid
        collections_json = db_inspector.list_collections_as_json()
        socketio.emit("db_collections_list", collections_json, to=session_id)

    @socketio.on("request_db_collection_data")
    @trace
    def handle_db_collection_data_request(data: dict) -> None:
        """Forwards a request for specific collection data to the db_inspector."""
        session_id = request.sid
        if collection_name := data.get("collection_name"):
            collection_data_json = db_inspector.get_collection_data_as_json(collection_name)
            socketio.emit("db_collection_data", collection_data_json, to=session_id)

    @socketio.on("user_confirmation")
    @trace
    def handle_user_confirmation(data: dict) -> None:
        """Receives a 'yes' or 'no' from the user and forwards it to a waiting event."""
        session_id = request.sid
        if event := confirmation_events.get(session_id):
            event.send(data.get("response"))

    @socketio.on("log_audit_event")
    @trace
    def handle_audit_log(data: dict) -> None:
        """Receives an audit log event from the client."""
        session_id = request.sid
        session_data = chat_sessions.get(session_id)
        session_name = session_data.name if session_data else "N/A"

        audit_log.log_event(
            event=data.get("event"),
            session_id=session_id,
            session_name=session_name,
            source=data.get("source"),
            destination=data.get("destination"),
            details=data.get("details"),
            control_flow=data.get("control_flow"),
        )
        
    @socketio.on('reset_tracer')
    @trace
    def handle_reset_tracer(data=None):
        """Handles a request from the scenario runner to reset the global tracer."""
        logging.info("Received request to reset global tracer.")
        global_tracer.reset()

    @socketio.on('get_trace_log')
    @trace
    def handle_get_trace_log(data=None):
        """
        Handles a request from the scenario runner to get the trace log
        and sends it back.
        """
        logging.info("Received request to get trace log.")
        session_id = request.sid
        trace_log = global_tracer.get_trace()
        socketio.emit("trace_log_response", {"trace": trace_log}, to=session_id)
