import json
import logging
from eventlet import tpool
from eventlet.event import Event
from tool_agent import execute_tool_command
from audit_logger import audit_log
import uuid
import debugpy
import re
import os
from datetime import datetime

confirmation_events = {}

def _log_turn_to_file(session_name, loop_id, turn_counter, role, content):
    """
    Logs the content of a turn to a structured file path in the .sandbox/TurnFiles directory.
    Creates directories as needed.
    """
    try:
        # Sanitize session_name to be a valid directory name
        safe_session_name = "".join(c for c in session_name if c.isalnum() or c in ['_', '-']).strip()
        if not safe_session_name:
            safe_session_name = "unnamed_session"

        # Define the directory path structure
        base_dir = os.path.join('.sandbox', 'TurnFiles', safe_session_name, loop_id)
        os.makedirs(base_dir, exist_ok=True)

        # Define the filename structure
        filename = f"{safe_session_name}_{loop_id}_{turn_counter}_{role}.txt"
        filepath = os.path.join(base_dir, filename)

        # Write the content to the file
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        logging.info(f"Successfully logged turn to {filepath}")
    except Exception as e:
        logging.error(f"Failed to log turn to file: {e}")

def _mask_payloads(text: str) -> str:
    """
    Finds all payload blocks (START @@... END @@...) and replaces them with an empty string.
    This prevents the JSON extraction logic from accidentally finding JSON within a payload.
    """
    # This regex finds all instances of "START @@PLACEHOLDER ... END @@PLACEHOLDER" and removes them.
    # It uses a backreference \1 to ensure the start and end placeholders match.
    # re.DOTALL ensures that '.' matches newlines, covering multi-line payloads.
    pattern = re.compile(r"START (@@\w+).*?END \1", re.DOTALL)
    return pattern.sub("", text)

def parse_agent_response(response_text: str) -> (str | None, dict | None, bool):
    """
    Parses a potentially messy agent response to separate prose from a valid command JSON.

    This function is designed to handle "mixed messages" containing both natural
    language text (prose) and a command in JSON format. It addresses several
    failure modes, including missing JSON fences, malformed JSON, and prose
    that might be mistaken for JSON.

    This version first masks payload blocks to prevent false positives during JSON extraction.

    Args:
        response_text: The raw string response from the agent.

    Returns:
        A tuple containing three elements:
        - The cleaned prose string (or None if no prose is found).
        - The parsed command JSON as a Python dictionary (or None if no valid JSON is found).
        - A boolean, `prose_is_empty`, which is True if the prose consists only of a timestamp and whitespace.
    """
    
    # --- Helper function for the new check ---
    def is_prose_effectively_empty(prose_string: str | None) -> bool:
        if not prose_string:
            return True
        # Regex to find a timestamp like [YYYY-MM-DD HH:MM:SS] at the start of the string
        timestamp_pattern = r'^\[\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\]\s*'
        # Remove the timestamp from the prose
        prose_without_timestamp = re.sub(timestamp_pattern, '', prose_string.strip())
        # The prose is considered empty if nothing remains after stripping whitespace
        return prose_without_timestamp.strip() == ""

    # Step 1: Create a sanitized version of the text with all payload blocks removed.
    sanitized_text = _mask_payloads(response_text)

    # Step 2: Attempt to find a command JSON within the sanitized text.
    # First, try finding a command enclosed in JSON fences.
    full_match_block, command_json_str = _extract_json_with_fences(sanitized_text)
    if full_match_block and command_json_str:
        try_parse = True
    else:
        # If no fences are found, fall back to brace counting on the sanitized text.
        full_match_block, command_json_str = _extract_json_with_brace_counting(sanitized_text)
        if full_match_block and command_json_str:
            try_parse = True
        else:
            try_parse = False
            
    # Step 3: If a potential command was found, parse it and construct the final prose.
    if try_parse:
        try:
            # First, try to load it as is.
            # If the agent provides a valid JSON with escaped newlines, this will work.
            command_json = json.loads(command_json_str)
        except json.JSONDecodeError:
            # Attempt to repair the JSON if initial parsing fails.
            command_json_str = _repair_json(command_json_str)
            try:
                command_json = json.loads(command_json_str)
            except json.JSONDecodeError:
                # If repair also fails, treat the whole original response as prose.
                prose_is_empty = is_prose_effectively_empty(response_text)
                return _clean_prose(response_text), None, prose_is_empty

        # Step 4: Construct the final prose by removing the command block from the *original* text.
        # This ensures payload blocks are preserved in the prose for the next stage.
        final_prose = response_text.replace(full_match_block, "", 1).strip()
        prose_is_empty = is_prose_effectively_empty(final_prose)
        return _clean_prose(final_prose), command_json, prose_is_empty

    # If no JSON command was found in the sanitized text, the entire original response is prose.
    prose_is_empty = is_prose_effectively_empty(response_text)
    return _clean_prose(response_text), None, prose_is_empty


def _extract_json_with_fences(text: str) -> (str | None, str | None):
    """
    Extracts the largest JSON block and its full enclosing ``` fences.
    Returns the full matched block and the inner JSON string.
    """
    pattern = r"(```json\s*\n?({.*?})\s*\n?```)"
    matches = list(re.finditer(pattern, text, re.DOTALL))
    
    if not matches:
        return None, None

    # Find the largest JSON block by the length of its content (group 2).
    largest_match = max(matches, key=lambda m: len(m.group(2)))
    
    full_block = largest_match.group(1)
    json_content = largest_match.group(2)
    
    return full_block, json_content


def _extract_json_with_brace_counting(text: str) -> (str | None, str | None):
    """
    Finds the largest valid JSON object in a string by counting braces.
    Returns the full JSON string if a valid one is found.
    """
    best_json_candidate = None
    
    # Find all potential start indices for a JSON object
    start_indices = [m.start() for m in re.finditer('{', text)]
    for start_index in start_indices:
        open_braces = 0
        in_string = False
        # We must check every possible end point for each start point
        for i, char in enumerate(text[start_index:]):
            if char == '\"' and (i == 0 or text[start_index + i - 1] != '\\'):
                in_string = not in_string
            if not in_string:
                if char == '{':
                    open_braces += 1
                elif char == '}':
                    open_braces -= 1
            if open_braces == 0:
                # We found a potential JSON object
                potential_json = text[start_index : start_index + i + 1]
                
                # Check if it's a valid JSON
                try:
                    # Use our repair function to increase chances of success
                    repaired_potential = _repair_json(potential_json)
                    json.loads(repaired_potential)
                    # If it's the best one so far (largest), store it
                    if not best_json_candidate or len(repaired_potential) > len(best_json_candidate):
                        best_json_candidate = repaired_potential
                        # The prose is what's before and after this candidate
                        prose_before = text[:start_index].strip()
                        prose_after = text[start_index + i + 1:].strip()
                        best_candidate_prose = f"{prose_before}\n{prose_after}".strip()
                except json.JSONDecodeError:
                    # Not a valid JSON, continue searching within this start_index
                    continue
                    
    return best_json_candidate, best_json_candidate


def _repair_json(s: str) -> str:
    """
    Attempts to repair a malformed JSON string by iteratively fixing errors
    based on feedback from the JSON parser. This approach is safer for complex
    string values than broad regex replacements.
    """
    s_before_loop = s
    max_iterations = 1000
    for _ in range(max_iterations):
        try:
            json.loads(s)
            # If parsing succeeds, the JSON is valid.
            return s
        except json.JSONDecodeError as e:
            error_fixed = False
            #import IPython; IPython.embed()
            # Fix 1: Unescaped control characters (e.g., newlines in string content).
            if "Invalid control character at" in e.msg:
                char_pos = e.pos
                char_to_escape = s[char_pos]
                escape_map = {'\n': '\\n', '\r': '\\r', '\t': '\\t'}
                if char_to_escape in escape_map:
                    s = s[:char_pos] + escape_map[char_to_escape] + s[char_pos+1:]
                    error_fixed = True

            # Fix 2: Unescaped double quotes inside a string.
            # This often leads to "Expecting ',' delimiter" or "Unterminated string".
            elif "Expecting" in e.msg or "Unterminated string" in e.msg:
                # Find the last quote before the error position.
                quote_pos = s.rfind('"', 0, e.pos)
                if quote_pos != -1:
                    # Check if it's already properly escaped by counting preceding backslashes.
                    p = quote_pos - 1
                    slashes = 0
                    while p >= 0 and s[p] == '\\':
                        slashes += 1
                        p -= 1
                    # If the number of preceding backslashes is even, the quote is not escaped.
                    if slashes % 2 == 0:
                        s = s[:quote_pos] + '\\' + s[quote_pos:]
                        error_fixed = True
            if not error_fixed:
                # If we can't identify a fix in this iteration, break the loop.
                return s_before_loop

    # If we exhausted iterations, return the last attempted state.
    return s

def _clean_prose(prose: str | None) -> str | None:
    """
    Utility to clean up the final prose string.
    """
    if prose:
        return prose.strip()
    return None

def _handle_payloads(prose, command_json):
    """
    Finds and replaces payload placeholders in a command's parameters
    with content defined in START/END blocks within the prose.
    """
    placeholders_found = []
    if not command_json or 'parameters' not in command_json or not prose:
        return prose, command_json, placeholders_found

    params = command_json['parameters']
    placeholders_to_process = [(k, v) for k, v in params.items() if isinstance(v, str) and v.startswith('@@')]

    for key, placeholder in placeholders_to_process:
        start_marker = f"START {placeholder}"
        end_marker = f"END {placeholder}"
        start_index = prose.find(start_marker)
        if start_index == -1:
            continue
        end_index = prose.find(end_marker, start_index)
        if end_index == -1:
            continue

        content_start = start_index + len(start_marker)
        payload_content = prose[content_start:end_index].strip()
        params[key] = payload_content
        placeholders_found.append(placeholder)
        logging.info(f"Successfully extracted payload for '{placeholder}'.")

    if placeholders_found:
        temp_prose = prose
        for placeholder in placeholders_found:
            pattern = re.compile(f"START {re.escape(placeholder)}.*?END {re.escape(placeholder)}", re.DOTALL)
            temp_prose = pattern.sub('', temp_prose)
        prose = temp_prose.strip()

    return prose, command_json, placeholders_found


def replay_history_for_client(socketio, session_id, session_name, history):
    """
    Parses the raw chat history and emits granular rendering events to the client.
    This version includes logic to clean payloads from prose for consistent rendering.
    """
    try:
        audit_log.log_event("History Replay Started", session_id=session_id, session_name=session_name, source="Orchestrator", destination="Client", details=f"Replaying {len(history)} turns.")
        socketio.emit('clear_chat_history', to=session_id)
        socketio.sleep(0.1)

        for item in history:
            role = item.get('role')
            raw_text = (item.get('parts', [{}])[0] or {}).get('text', '')
            if not raw_text or not raw_text.strip():
                continue

            if role == 'user':
                # --- SURGICAL FIX START ---
                is_tool_result = False
                # First, check for prefixed tool results (older format)
                if raw_text.startswith(('TOOL_RESULT:', 'OBSERVATION:', 'Tool Result:')):
                    try:
                        json_str = raw_text[raw_text.find('{'):]
                        tool_result = json.loads(json_str)
                        log_message = tool_result.get('message', 'Tool action completed.')
                        socketio.emit('tool_log', {'data': f"[{log_message}]"}, to=session_id)
                        is_tool_result = True
                    except (json.JSONDecodeError, IndexError):
                        socketio.emit('tool_log', {'data': f"[{raw_text}]"}, to=session_id)
                        is_tool_result = True
                
                # If not a prefixed result, try parsing the whole string as JSON (newer format)
                if not is_tool_result:
                    try:
                        tool_result = json.loads(raw_text)
                        if isinstance(tool_result, dict) and 'status' in tool_result:
                            log_message = tool_result.get('message', 'Tool action completed.')
                            socketio.emit('tool_log', {'data': f"[{log_message}]"}, to=session_id)
                            is_tool_result = True
                    except (json.JSONDecodeError, TypeError):
                        pass # It's not a pure JSON object, so it's a regular user message.
                
                if is_tool_result:
                    continue
                
                # If it's not any kind of tool result, treat it as a standard user message
                if not raw_text.startswith('USER_CONFIRMATION:'):
                    socketio.emit('log_message', {'type': 'user', 'data': raw_text}, to=session_id)
                # --- SURGICAL FIX END ---
            
            elif role == 'model':

                prose, command_json, prose_is_empty = parse_agent_response(raw_text)
                
                if prose_is_empty and not command_json:
                    continue

                # This crucial step cleans the prose of any payload blocks.
                cleaned_prose, _, _ = _handle_payloads(prose, command_json)
                
                final_message_for_display = ""
                
                # Determine what to display based on the command and cleaned prose.
                if command_json:
                    action = command_json.get('action')
                    if action in ['respond', 'task_complete']:
                        response_param_text = command_json.get('parameters', {}).get('response', '') or ""
                        prose_text = cleaned_prose or ""
                        
                        if len(prose_text.strip()) > len(response_param_text.strip()):
                            final_message_for_display = prose_text
                        else:
                            final_message_for_display = response_param_text
                elif cleaned_prose:
                    # If there's no command, the cleaned prose is the final answer.
                    final_message_for_display = cleaned_prose

                # Render the messages based on the processed data
                if final_message_for_display:
                    socketio.emit('log_message', {'type': 'final_answer', 'data': final_message_for_display}, to=session_id)
                elif cleaned_prose: # This handles cases where prose is an intro to a command.
                    socketio.emit('log_message', {'type': 'info', 'data': cleaned_prose}, to=session_id)
                
                # Handle non-message actions like confirmation prompts
                if command_json and command_json.get('action') == 'request_confirmation':
                    prompt = command_json.get('parameters', {}).get('prompt')
                    if prompt:
                        socketio.emit('log_message', {'type': 'system_confirm', 'data': prompt}, to=session_id)

            socketio.sleep(0.01)
    except Exception as e:
        logging.error(f"Error during history replay for session {session_name}: {e}")
        socketio.emit('log_message', {'type': 'error', 'data': f"Failed to replay history: {e}"}, to=session_id)


def execute_reasoning_loop(socketio, session_data, initial_prompt, session_id, chat_sessions, model, api_stats):
    loop_id = str(uuid.uuid4())

    def get_current_session_name():
        return chat_sessions.get(session_id, {}).get('name')
    
    audit_log.log_event(
        event="Reasoning Loop Started",
        session_id=session_id,
        session_name=get_current_session_name(),
        loop_id=loop_id,
        source="Orchestrator",
        destination="Orchestrator",
        details={"initial_prompt": initial_prompt},
        control_flow=None
    )

    try:
        current_prompt = initial_prompt
        destruction_confirmed = False

        if not isinstance(session_data, dict):
            logging.error(f"Session data for {session_id} is not a dictionary.")
            audit_log.log_event(
                event="Socket.IO Emit: log_message",
                session_id=session_id,
                session_name=get_current_session_name(),
                loop_id=loop_id,
                source="Orchestrator",
                destination="Client",
                details={'type': 'error', 'data': f"Session data is not a dictionary."},
                control_flow="Return"
            )
            socketio.emit('log_message', {'type': 'error', 'data': f"Session data is not a dictionary."}, to=session_id)
            return

        chat = session_data.get('chat')
        memory = session_data.get('memory')

        if not chat or not memory:
            logging.error(f"Could not find chat or memory object for session {session_id}.")
            audit_log.log_event(
                event="Socket.IO Emit: log_message",
                session_id=session_id,
                session_name=get_current_session_name(),
                loop_id=loop_id,
                source="Orchestrator",
                destination="Client",
                details={'type': 'error', 'data': 'Critical error: Chat or Memory session object not found.'},
                control_flow="Return"
            )
            socketio.emit('log_message', {'type': 'error', 'data': 'Critical error: Chat or Memory session object not found.'}, to=session_id)
            return

        observation_template = "Tool Result: {tool_result_json}"

        for i in range(100):
            socketio.sleep(0)
            
            audit_log.log_event(
                event=f"Beginning iteration {i} of reasoning loop.",
                session_id=session_id,
                session_name=get_current_session_name(),
                loop_id=loop_id,
                source="Orchestrator",
                destination="Orchestrator",
                details={},
                control_flow=None
            )

            retrieved_context = None #memory.get_context_for_prompt(current_prompt)

            final_prompt = current_prompt
            if retrieved_context:
                context_str = "\n".join(retrieved_context)
                final_prompt = (
                    "CONTEXT FROM PAST CONVERSATIONS:\n"
                    f"{context_str}\n\n"
                    "Based on the above context, please respond to the following prompt:\n"
                    f"{current_prompt}"
                )
                log_message = f"Augmented prompt with {len(retrieved_context)} documents from memory."
                logging.info(log_message)
                audit_log.log_event(
                    event=log_message,
                    session_id=session_id,
                    session_name=get_current_session_name(),
                    loop_id=loop_id,
                    source="Orchestrator",
                    destination="Orchestrator",
                    details={},
                    control_flow=None
                )

            audit_log.log_event(
                event='memory.add_turn("user", current_prompt)',
                session_id=session_id,
                session_name=get_current_session_name(),
                loop_id=loop_id,
                source="Orchestrator",
                destination="Memory Manager",
                details={"current_prompt": current_prompt},
                control_flow=None
            )
            memory.add_turn("user", current_prompt)

            # Log the prompt sent to the agent
            #_log_turn_to_file(get_current_session_name(), loop_id, i, "user", final_prompt)

            audit_log.log_event(
                event="Gemini API Call Sent",
                session_id=session_id,
                session_name=get_current_session_name(),
                loop_id=loop_id,
                source="Orchestrator",
                destination="Gemini",
                details={"prompt": final_prompt},
                control_flow="Send"
            )

            response = tpool.execute(chat.send_message, final_prompt)
            
            audit_log.log_event(
                event="Gemini API Response Received",
                session_id=session_id,
                session_name=get_current_session_name(),
                loop_id=loop_id,
                source="Gemini",
                destination="Orchestrator",
                details={"response_text": response.text},
                control_flow="Receive"
            )

            if response.usage_metadata:
                api_stats['total_calls'] += 1
                api_stats['total_prompt_tokens'] += response.usage_metadata.prompt_token_count
                api_stats['total_completion_tokens'] += response.usage_metadata.candidates_token_count
                socketio.emit('api_usage_update', api_stats)
            
            # --- Idempotent Timestamping ---
            response_text = response.text
            # Check if a timestamp of the form [YYYY-MM-DD HH:MM:SS] already exists
            if not re.match(r'^\[\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\]', response_text):
                timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                response_text = f"[{timestamp}] {response_text}"

            # Log the raw response from the agent
            #_log_turn_to_file(get_current_session_name(), loop_id, i, "model", response_text)

            audit_log.log_event(
                event='memory.add_turn("model", response_text)',
                session_id=session_id,
                session_name=get_current_session_name(),
                loop_id=loop_id,
                source="Orchestrator",
                destination="Memory Manager",
                details={"response_text": response_text},
                control_flow=None
            )
            memory.add_turn("model", response_text)

            prose, command_json, prose_is_empty = parse_agent_response(response_text)
            audit_log.log_event(
                event='parse_agent_response() completed.',
                session_id=session_id,
                session_name=get_current_session_name(),
                loop_id=loop_id,
                source="Orchestrator",
                destination="Orchestrator",
                details={"prose": prose, "command_json": command_json, "prose_is_empty": prose_is_empty},
                control_flow=None
            )

            prose, command_json, placeholders_found = _handle_payloads(prose, command_json)
            if placeholders_found:
                audit_log.log_event(
                    event='_handle_payloads() completed.',
                    session_id=session_id,
                    session_name=get_current_session_name(),
                    loop_id=loop_id,
                    source="Orchestrator",
                    destination="Orchestrator",
                    details={ "prose": prose, "command_json": command_json},
                    control_flow=None
                )

            if prose and command_json:    
                command_json['attachment'] = prose   

            if not command_json:
                logging.warning(f"Could not decode JSON from model response. Treating as plain text.")
                command_json = {"action": "respond", "parameters": {"response": response_text}}

            action = command_json.get("action")

            # --- REFACTORED AND UNIFIED MESSAGE HANDLING LOGIC ---
            final_message_to_user = ""
            
            # Case 1: The action is a final response ('respond' or 'task_complete').
            if action in ['respond', 'task_complete']:
                prose_text = command_json.get('attachment', '') or ""
                response_param_text = command_json.get('parameters', {}).get('response', '') or ""
                
                # Determine the definitive message to display
                if len(prose_text.strip()) > len(response_param_text.strip()):
                    final_message_to_user = prose_text
                else:
                    final_message_to_user = response_param_text
                
                # Send the final message if it's not empty
                if final_message_to_user and final_message_to_user.strip() and not prose_is_empty:
                    socketio.emit('log_message', {'type': 'final_answer', 'data': final_message_to_user}, to=session_id)
                
                if action == 'task_complete':
                    logging.info(f"Agent initiated task_complete. Ending loop for session {session_id}.")
                
                return # Terminate the loop after sending the final message.

            # Case 2: The action is a tool command, which may have preceding prose.
            destructive_actions = ['delete_file', 'delete_session']
            if action in destructive_actions and not destruction_confirmed:
                err_msg = f"Action '{action}' is destructive and requires user confirmation. I must use 'request_confirmation' first."
                logging.warning(err_msg)
                error_payload = {'status': 'error', 'message': err_msg}
                current_prompt = observation_template.format(tool_result_json=json.dumps(error_payload))
                destruction_confirmed = False
                continue

            if action == 'request_confirmation':
                prompt_text = command_json.get('parameters', {}).get('prompt', 'Are you sure?')
                # Send the introductory prose first, if it exists
                if command_json.get('attachment'):
                    prose_text = command_json.get('attachment', '')
                    if prose_text and prose_text.strip() and not prose_is_empty:
                        socketio.emit('log_message', {'type': 'info', 'data': prose_text}, to=session_id)

                confirmation_event = Event()
                confirmation_events[session_id] = confirmation_event
                audit_log.log_event("Socket.IO Emit: request_user_confirmation", session_id=session_id, session_name=get_current_session_name(), loop_id=loop_id, source="Orchestrator", destination="Client", observers=["User", "Orchestrator"], details={'prompt': prompt_text})
                socketio.emit('request_user_confirmation', {'prompt': prompt_text}, to=session_id)
                user_response = confirmation_event.wait()
                confirmation_events.pop(session_id, None)
                if user_response == 'yes':
                    destruction_confirmed = True
                else:
                    destruction_confirmed = False
                current_prompt = f"USER_CONFIRMATION: '{user_response}'"
                continue

            # --- TOOL EXECUTION AND RE-ORDERED RESPONSE ---
            audit_log.log_event(
                event="Tool Agent Call Sent",
                session_id=session_id,
                session_name=get_current_session_name(),
                loop_id=loop_id,
                source="Orchestrator",
                destination="Tool Agent",
                details=command_json
            )
            
            tool_result = execute_tool_command(command_json, socketio, session_id, chat_sessions, model, loop_id)            
            
            audit_log.log_event(
                event="Tool Agent Execution Finished",
                session_id=session_id,
                session_name=get_current_session_name(),
                loop_id=loop_id,
                source="Orchestrator",
                destination="Orchestrator",
                details=tool_result
            )

            destruction_confirmed = False

            # STEP 1: Log the tool result to the client's tool log.
            if tool_result.get('status') == 'success':
                log_message = tool_result.get('message', f"Tool '{action}' executed successfully.")
            else:
                log_message = tool_result.get('message', f"Tool '{action}' failed.")

            # Log the result to the client's tool log.
            audit_log.log_event(
                event="Socket.IO Emit: tool_log",
                session_id=session_id,
                session_name=get_current_session_name(),
                loop_id=loop_id,
                source="Orchestrator",
                destination="Client",
                details={'data': f"[{log_message}]"}
            )
            socketio.emit('tool_log', {'data': f"[{log_message}]"}, to=session_id)

            # Special case for session loading, which shouldn't pause.
            if action == "load_session":
                return

            # STEP 2: Now, send the agent's "thinking out loud" prose that came with the command.
            if command_json.get('attachment'):
                prose_text = command_json.get('attachment', '')
                if prose_text and prose_text.strip() and not prose_is_empty:
                    socketio.emit('log_message', {'type': 'info', 'data': prose_text}, to=session_id)

            # STEP 3: Finally, request confirmation to proceed.
            prompt_text = "Tool execution complete. May I proceed?"
            confirmation_event = Event()
            confirmation_events[session_id] = confirmation_event
            socketio.emit('request_user_confirmation', {'prompt': prompt_text}, to=session_id)
            user_response = confirmation_event.wait()
            confirmation_events.pop(session_id, None)

            if user_response != 'yes':
                logging.info(f"User halted execution after tool action. Ending loop for session {session_id}.")
                socketio.emit('log_message', {'type': 'info', 'data': "Execution halted by user."}, to=session_id)
                break # Use break to cleanly exit the loop and wait for new user input.
            
            current_prompt = observation_template.format(tool_result_json=json.dumps(tool_result))

    except Exception as e:
        logging.exception("An error occurred in the reasoning loop.")
        socketio.emit('log_message', {'type': 'error', 'data': f"An error occurred during reasoning: {str(e)}"}, to=session_id)
    finally:
        audit_log.log_event("Reasoning Loop Ended", session_id=session_id, session_name=get_current_session_name(), loop_id=loop_id, source="Orchestrator", destination="Orchestrator", observers=["Orchestrator"])