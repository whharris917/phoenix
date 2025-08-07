"""
Core cognitive engine for the AI agent.

This module contains the primary reasoning loop that drives the agent's behavior.
It orchestrates the interaction between the agent's memory, the generative model,
and the tool execution system, forming the "brain" of the application.
"""
from eventlet import tpool
from eventlet.event import Event
from utils import get_timestamp
import json
import logging
import uuid
import re
from tool_agent import execute_tool_command
from data_models import ToolCommand, ParsedAgentResponse
from session_models import ActiveSession
from response_parser import parse_agent_response, _handle_payloads, is_prose_effectively_empty
from config import ABSOLUTE_MAX_ITERATIONS_REASONING_LOOP, NOMINAL_MAX_ITERATIONS_REASONING_LOOP
from tracer import trace, log_event

# A dictionary to hold event objects for user confirmation, keyed by session_id.
# This allows the reasoning loop to pause and wait for user input.
confirmation_events: dict[str, Event] = {}

@trace
def _emit_agent_message(socketio, session_id: str, message_type: str, content: str) -> None:
    """
    A small wrapper to emit a formatted message to the client.

    This helper ensures that empty or whitespace-only messages are not sent,
    keeping the client-side log clean.

    Args:
        socketio: The SocketIO server instance for communication.
        session_id: The unique session ID of the target client.
        message_type: The category of the message (e.g., 'final_answer', 'info').
        content: The text content of the message.
    """
    if content and content.strip():
        socketio.emit("log_message", {"type": message_type, "data": content}, to=session_id)

@trace
def _process_model_response(response_text: str) -> ParsedAgentResponse:
    """
    Parses raw model text into a structured ParsedAgentResponse object.
    
    This function acts as a crucial translation layer between the raw output of
    the generative model and the structured data the orchestrator works with.
    It isolates parsing, handles payload extraction, attaches prose to the
    command for context, and creates a fallback command if necessary.

    Args:
        response_text: The raw, timestamped text from the generative model.

    Returns:
        The fully processed ParsedAgentResponse object, ready for rendering
        and execution.
    """
    # Step 1: Perform the initial, complex parsing of the raw text.
    parsed = parse_agent_response(response_text)
    
    # Step 2: If a command was found, handle any embedded payload definitions.
    if parsed.command:
        # This mutates the parsed object in place.
        # It finds @@PLACEHOLDER definitions in the prose, extracts the content,
        # injects it into the command's parameters, and cleans the prose.
        prose, command = _handle_payloads(parsed.prose, parsed.command)
        
        # The cleaned prose is attached to the command for contextual awareness
        # by the tool agent and for rendering by the renderer.
        command.attachment = prose
        parsed.prose = prose
        parsed.command = command

    # Step 3: If no command could be decoded, create a fallback 'respond' command.
    # This ensures the system is resilient to malformed model outputs and
    # always has a valid command object to work with.
    if not parsed.command:
        parsed.command = ToolCommand(action="respond", parameters={"response": response_text})

    return parsed

@trace
def _render_agent_turn(socketio, session_id: str, parsed_response: ParsedAgentResponse, is_live: bool = False) -> None:
    """
    Renders the agent's turn to the client from a ParsedAgentResponse object.

    This function is highly declarative, using the pre-calculated attributes of the
    ParsedAgentResponse object to render the UI without further calculations.
    It translates the agent's internal command into a user-facing message,
    confirmation prompt, or informational text.

    Args:
        socketio: The SocketIO server instance.
        session_id: The client's unique session ID.
        parsed_response: The structured response object from _process_model_response.
        is_live: A flag indicating if this is a live turn (requiring a real
                 confirmation prompt) or a replayed one from history.
    """   

    command = parsed_response.command
    prose = command.attachment or ""

    # Case 1: The command is a final answer for the user.
    if command.action in ["respond", "task_complete"]:
        response_param = command.parameters.get("response", "")
        # The definitive message is whichever is longer: the prose or the 'response' parameter.
        final_message = response_param if len(response_param) > len(prose) else prose
        
        # This prevents both empty and timestamp-only messages from being displayed.
        if not is_prose_effectively_empty(final_message):
             _emit_agent_message(socketio, session_id, "final_answer", final_message)

    # Case 2: The command is a request for user confirmation.
    elif command.action == "request_confirmation":
        # Display any introductory prose first.
        if not parsed_response.is_prose_empty:
            _emit_agent_message(socketio, session_id, "info", prose)
        
        prompt = command.parameters.get("prompt", "Are you sure?")
        # If this is a live reasoning loop, show interactive Yes/No buttons.
        if is_live:
            socketio.emit("request_user_confirmation", {"prompt": prompt}, to=session_id)
        # If replaying history, just show the prompt that was asked.
        else:
            _emit_agent_message(socketio, session_id, "system_confirm", prompt)
            
    # Case 3: All other commands (tool calls) may have preceding prose.
    else:
        # This displays the "thinking" or introductory text before a tool is called.
        if not parsed_response.is_prose_empty:
            _emit_agent_message(socketio, session_id, "info", prose)

@trace
def execute_reasoning_loop(
    socketio,
    session_data: ActiveSession,
    initial_prompt: str,
    session_id: str,
    chat_sessions: dict[str, ActiveSession],
    haven_proxy: object,
) -> None:
    """
    Executes the main cognitive loop for the agent.

    This loop is the heart of the agent, driving a cycle of thought and action:
    1. Augment a prompt with context from memory (RAG).
    2. Call the generative model.
    3. Process the model's response into a command.
    4. Render the agent's "thought" or action to the user.
    5. Execute the command.
    6. Use the result of the action as the prompt for the next cycle.
    This continues until the task is complete or a limit is reached.

    Args:
        socketio: The SocketIO server instance for real-time client communication.
        session_data: The active session object containing memory and chat proxies.
        initial_prompt: The user's initial prompt that kicks off the loop.
        session_id: The client's unique session ID.
        chat_sessions: A dictionary of all active sessions, necessary for the
                       agent to perform session management tools (load, save, etc.).
        haven_proxy: The proxy object for the Haven service, which hosts the model.
    """
    loop_id = str(uuid.uuid4())
    current_prompt = initial_prompt
    destruction_confirmed = False # State flag for approved destructive actions.

    try:
        chat = session_data.chat
        memory = session_data.memory

        # The core cognitive loop, limited to a max number of iterations for safety.
        for i in range(ABSOLUTE_MAX_ITERATIONS_REASONING_LOOP):
            log_event(f"BEGINNING ITERATION {i} of RESONING LOOP", {})
            socketio.sleep(0)  # Yield to other greenlets, keeping the server responsive.

            # --- Step 1: Prepare the Prompt ---
            # Augment the current prompt with relevant context from long-term memory (RAG).
            final_prompt = memory.prepare_augmented_prompt(current_prompt)

            # Add iteration information to the final prompt to give the model awareness of the loop's state.
            final_prompt_with_iteration = (
                f"This is iteration {i + 1} of {NOMINAL_MAX_ITERATIONS_REASONING_LOOP} of the reasoning loop.\n"
                f"You MUST issue a `respond` command on or before the final iteration.\n\n"
                f"{final_prompt}"
            )
            # Persist the user-side turn to memory for auditing and future context.
            memory.add_turn("user", current_prompt, augmented_prompt=final_prompt_with_iteration)

            # --- Step 2: Call the Model ---
            # Send the final, fully-formed prompt to the generative model.
            response = tpool.execute(chat.send_message, final_prompt_with_iteration)
            response_text = response.text
            
            # Ensure the response has a timestamp for consistent logging format.
            if not re.match(r"^\[\d{2}[A-Z]{3}\d{4}_\d{2}\d{2}\d{2}[AP]M\]", response_text):
                response_text = f"[{get_timestamp()}] {response_text}"

            # Persist the raw model response to memory.
            memory.add_turn("model", response_text)

            # --- Step 3: Process and Render the Response ---
            # Process the raw text once to get a structured ParsedAgentResponse object.
            parsed_response = _process_model_response(response_text)
            
            # Pass the entire structured object to the renderer to update the client UI.
            _render_agent_turn(socketio, session_id, parsed_response, is_live=True)

            action = parsed_response.command.action

            # --- Step 4: Handle Loop Control and Termination ---
            # Force agent to respond if it exceeds the nominal iteration limit.
            if i >= NOMINAL_MAX_ITERATIONS_REASONING_LOOP and action != "respond":
                current_prompt = (
                    "WARNING: You have exceeded the nominal iteration limit."
                    "You MUST use the `respond` command to issue a final response to the user."
                )
                continue

            # If the agent issues a final response, the loop is complete.
            if action in ["respond", "task_complete"]:
                logging.info(f"Agent has issued a response. Terminating reasoning loop for session {session_id}.")
                return

            # --- Step 5: Handle Confirmation Flow for Destructive Actions ---
            if action in ["delete_file", "delete_session"] and not destruction_confirmed:
                err_msg = f"Action '{action}' is destructive. Use 'request_confirmation' first."
                logging.warning(err_msg)
                current_prompt = f"Tool Result: {json.dumps({'status': 'error', 'message': err_msg})}"
                continue

            if action == "request_confirmation":
                # Pause the loop and wait for the user to respond 'yes' or 'no' via the UI.
                confirmation_event = Event()
                confirmation_events[session_id] = confirmation_event
                user_response = confirmation_event.wait()
                confirmation_events.pop(session_id, None)
                
                destruction_confirmed = user_response == "yes"
                current_prompt = f"USER_CONFIRMATION: '{user_response}'"
                continue

            # --- Step 6: Execute Tool and Prepare for Next Iteration ---
            # Execute the requested tool command in a separate thread.
            tool_result = execute_tool_command(parsed_response.command, socketio, session_id, chat_sessions, haven_proxy, loop_id)
            
            # Reset confirmation status after any tool call.
            destruction_confirmed = False
            
            socketio.emit("tool_log", {"data": f"[{tool_result.message}]"}, to=session_id)

            # If the session was changed (e.g., loaded), this loop's context is now invalid. Terminate.
            if action == "load_session":
                return

            # The result of the tool becomes the input for the next iteration of the loop.
            current_prompt = f"Tool Result: {tool_result.model_dump_json()}"

    except Exception as e:
        # Gracefully handle any unexpected errors in the loop.
        error_message = f"An error occurred in the reasoning loop: {e}"
        logging.exception(error_message)
        socketio.emit("log_message", {"type": "error", "data": error_message}, to=session_id)
    finally:
        # This will run regardless of whether the loop succeeded or failed.
        logging.info(f"Reasoning Loop ended for session {session_id}.")
