from eventlet import tpool
from eventlet.event import Event
from datetime import datetime
import json, logging, uuid, debugpy, re, os
from tool_agent import execute_tool_command

ABSOLUTE_MAX_ITERATIONS_REASONING_LOOP = 10
NOMINAL_MAX_ITERATIONS_REASONING_LOOP = 3

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
    # It uses a backreference \\1 to ensure the start and end placeholders match.
    # re.DOTALL ensures that '.' matches newlines, covering multi-line payloads.
    pattern = re.compile(r"START (@@\\w+).*?END \\1", re.DOTALL)
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
        timestamp_pattern = r'^\\[\\d{4}-\\d{2}-\\d{2} \\d{2}:\\d{2}:\\d{2}\\]\\s*'
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
    pattern = r"(```json\\s*\\n?({.*?})\\s*\\n?```)"
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
            if char == '\"' and (i == 0 or text[start_index + i - 1] != '\\\\'):
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
                        best_candidate_prose = f"{prose_before}\\n{prose_after}".strip()
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
                escape_map = {'\\n': '\\\\n', '\\r': '\\\\r', '\\t': '\\\\t'}
                if char_to_escape in escape_map:
                    s = s[:char_pos] + escape_map[char_to_escape] + s[char_pos+1:]
                    error_fixed = True

            # Fix 2: Unescaped double quotes inside a string.
            # This often leads to "Expecting ',' delimiter" or "Unterminated string".
            elif "Expecting" in e.msg or "Unterminated string" in e.msg:
                # Find the last quote before the error position.
                quote_pos = s.rfind('\"', 0, e.pos)
                if quote_pos != -1:
                    # Check if it's already properly escaped by counting preceding backslashes.
                    p = quote_pos - 1
                    slashes = 0
                    while p >= 0 and s[p] == '\\\\':
                        slashes += 1
                        p -= 1
                    # If the number of preceding backslashes is even, the quote is not escaped.
                    if slashes % 2 == 0:
                        s = s[:quote_pos] + '\\\\' + s[quote_pos:]
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
        return prose, command_json

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

    return prose, command_json

def _emit_agent_message(socketio, session_id, message_type, content):
    """A small wrapper to emit a formatted message to the client."""
    if content and content.strip():
        socketio.emit('log_message', {'type': message_type, 'data': content}, to=session_id)

def _render_user_turn(socketio, session_id, raw_text):
    """Parses and renders a 'user' turn from history for high-fidelity replay."""
    is_tool_result = False
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
    else:
        try:
            tool_result = json.loads(raw_text)
            if isinstance(tool_result, dict) and 'status' in tool_result:
                log_message = tool_result.get('message', 'Tool action completed.')
                socketio.emit('tool_log', {'data': f"[{log_message}]"}, to=session_id)
                is_tool_result = True
        except (json.JSONDecodeError, TypeError):
            pass

    if not is_tool_result and not raw_text.startswith('USER_CONFIRMATION:'):
        # In the original logic, user messages were sent with type 'user'.
        # The new client-side logic uses 'display_user_prompt', but for fidelity
        # with original history, we can stick to the 'log_message' event.
        socketio.emit('log_message', {'type': 'user', 'data': raw_text}, to=session_id)

def _process_and_render_model_turn(socketio, session_id, timestamped_response_text, is_live=False):
    """
    Parses and renders a 'model' turn, handling prose, commands, and confirmations.
    This is used for both live rendering and high-fidelity history replay.
    """

    # --- BEGINNING OF AGENT RESPONSE PARSING ---

    # Separate prose from command_json, attempt to repair command_json
    prose, command_json, prose_is_empty = parse_agent_response(timestamped_response_text)

    # Strip placeholder definitions from prose and move to command_json
    prose, command_json = _handle_payloads(prose, command_json)

    # Move prose into command_json as attachment if command_json exists
    if prose and command_json: 
        command_json['attachment'] = prose

    # If command_json does not exist, create it as a `response` command with timestamped model response text
    if not command_json:
        logging.warning(f"Could not decode JSON from model response. Treating as plain text.")
        command_json = {"action": "respond", "parameters": {"response": timestamped_response_text}}

    # At this point, command_json exist and any prose is contained in its attachment or response fields
    # The prose variable is no longer needed. However, the prose contained within command_json may contain only a timestamp

    # --- END OF AGENT RESPONSE PARSING ---

    action = command_json.get("action")

    final_message = ""

    # Case 1: The action is a final response ('respond' or 'task_complete')
    if action in ['respond', 'task_complete']: # task_complete is a legacy command
        # Compare the length of the prose attachment and the response parameter
        prose_text = command_json.get('attachment', '') or ""
        response_param_text = command_json.get('parameters', {}).get('response', '') or ""
        
        # Determine the definitive message to display
        if len(prose_text.strip()) > len(response_param_text.strip()):
            final_message = prose_text
        else:
            final_message = response_param_text
        
        # Send the final message if it's not empty
        if not prose_is_empty:
            _emit_agent_message(socketio, session_id, 'final_answer', final_message)
        
    # Case 2: The action is a tool command, which may have preceding prose.
    elif action == 'request_confirmation':
        if prose:
            _emit_agent_message(socketio, session_id, 'info', prose)
        prompt = command_json.get('parameters', {}).get('prompt', 'Are you sure?')
        if is_live:
            socketio.emit('request_user_confirmation', {'prompt': prompt}, to=session_id)
        else:
            _emit_agent_message(socketio, session_id, 'system_confirm', prompt)
    else: 
        if prose and not prose_is_empty:
            _emit_agent_message(socketio, session_id, 'info', prose)

    return(command_json)

def replay_history_for_client(socketio, session_id, session_name, history):
    """
    Parses the raw chat history and emits granular rendering events to the client.
    This version includes logic to clean payloads from prose for consistent rendering.
    """
    try:
        socketio.emit('clear_chat_history', to=session_id)
        socketio.sleep(0.1)

        for item in history:
            role = item.get('role')
            raw_text = (item.get('parts', [{}])[0] or {}).get('text', '')
            if not raw_text or not raw_text.strip():
                continue

            if role == 'user':
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
            
            elif role == 'model':
                prose, command_json, prose_is_empty = parse_agent_response(raw_text)
                
                if prose_is_empty:
                    continue

                # This crucial step cleans the prose of any payload blocks.
                cleaned_prose, _ = _handle_payloads(prose, command_json)
                
                final_message_for_display = ""
                
                # Determine what to display based on the command and cleaned prose.
                if command_json:
                    action = command_json.get('action')
                    if action in ['respond', 'task_complete']: # task_complete is a legacy command
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
                        socketio.emit('log_message', {'type': 'system_confirm_replayed', 'data': prompt}, to=session_id)

            socketio.sleep(0.01)
    except Exception as e:
        logging.error(f"Error during history replay for session {session_name}: {e}")
        socketio.emit('log_message', {'type': 'error', 'data': f\"Failed to replay history: {e}\"}, to=session_id)

def execute_reasoning_loop(socketio, session_data, initial_prompt, session_id, chat_sessions, haven_proxy, loop_id=None):
    loop_id = str(uuid.uuid4())

    # implement A loop, B loop, C loops strategy 
    # A: starts with message from user
    # B: starts with response that tool was successful
    # C: starts with response that tool failed
    # D: attempt to fix fail

    try:
        current_prompt = initial_prompt
        destruction_confirmed = False

        # --- NEW: Re-fetch session data on each loop to ensure context is fresh ---
        #session_data = chat_sessions.get(session_id)
        if not isinstance(session_data, dict):
            error_message = f"Session data for {session_id} is not a dictionary."
            logging.error(error_message)
            socketio.emit('log_message', {'type': 'error', 'data': error_message}, to=session_id)
            return

        chat = session_data.get('chat')
        memory = session_data.get('memory')

        if not chat or not memory:
            error_message = f"Could not find chat or memory object for session {session_id}."
            logging.error(error_message)
            socketio.emit('log_message', {'type': 'error', 'data': error_message}, to=session_id)
            return

        observation_template = "Tool Result: {tool_result_json}"

        for i in range(ABSOLUTE_MAX_ITERATIONS_REASONING_LOOP):
            socketio.sleep(0)

            # retrieved_context = memory.get_context_for_prompt(current_prompt)

            final_prompt = current_prompt

            final_prompt = (
                f"This is iteration {i+1} of {NOMINAL_MAX_ITERATIONS_REASONING_LOOP} of the reasoning loop.\\n"
                f"You MUST issue a resonse to the user on or before the final iteration.\\n"
                f"The prompt for the current iteration is below:\\n\\n"
                f\"{final_prompt}\"
            )

            """
            if retrieved_context:
                context_str = "\\n".join(retrieved_context)
                final_prompt = (
                    "CONTEXT FROM PAST CONVERSATIONS:\\n"
                    f"{context_str}\\n\\n"
                    "Based on the above context, please respond to the following prompt:\\n"
                    f"{current_prompt}"
                )
                log_message = f"Augmented prompt with {len(retrieved_context)} documents from memory."
                logging.info(log_message)
            """

            memory.add_turn("user", current_prompt)

            # Get raw response text from model
            response = tpool.execute(chat.send_message, final_prompt)
            response_text = response.text
            
            # Check if timestamp of form [YYYY-MM-DD HH:MM:SS] already exists
            # If not, add timestamp to beginning of response text
            if not re.match(r'^\\[\\d{4}-\\d{2}-\\d{2} \\d{2}:\\d{2}:\\d{2}\\]', response_text):
                timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                response_text = f"[{timestamp}] {response_text}"

            # Save timestamped response text to memory database
            memory.add_turn("model", response_text)

            command_json = _process_and_render_model_turn(socketio, session_id, response_text, is_live=True)

            action = command_json.get("action")

            if i >= NOMINAL_MAX_ITERATIONS_REASONING_LOOP and not action == "respond":
                current_prompt = "WARNING: You have exceeded the maximum number of allowed reasoning loop iterations. You MUST use the `respond` command to issue a response to the user and terminate this reasoning loop. Please note that any command or prose you sent during your last iteration was not executed or delivered to the user."
                continue

            # Case 1: The action is a final response ('respond' or 'task_complete')
            if action in ['respond', 'task_complete']: # task_complete is a legacy command
                # Response was already sent to client in _process_and_render_model_turn()
                logging.info(f"Agent has issued a response. Terminating reasoning loop for session {session_id}.")
                return # Terminate reasoning loop

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
                # Prompt and prose (if present) already sent to client in _process_and_render_model_turn()
                confirmation_event = Event()
                confirmation_events[session_id] = confirmation_event
                #socketio.emit('request_user_confirmation', {'prompt': prompt_text}, to=session_id)
                user_response = confirmation_event.wait()
                confirmation_events.pop(session_id, None)
                if user_response == 'yes':
                    destruction_confirmed = True
                else:
                    destruction_confirmed = False
                current_prompt = f"USER_CONFIRMATION: '{user_response}'"
                continue

            # --- TOOL EXECUTION AND RE-ORDERED RESPONSE ---
            
            tool_result = execute_tool_command(command_json, socketio, session_id, chat_sessions, haven_proxy, loop_id)            

            destruction_confirmed = False

            # STEP 1: Log the tool result to the client's tool log.
            if tool_result.get('status') == 'success':
                log_message = tool_result.get('message', f"Tool '{action}' executed successfully.")
            else:
                log_message = tool_result.get('message', f"Tool '{action}' failed.")
            socketio.emit('tool_log', {'data': f"[{log_message}]"}, to=session_id)

            # Special case for session loading, which shouldn't pause.
            if action == "load_session":
                return

            """
            # STEP 2: Now, send the agent's \"thinking out loud\" prose that came with the command.
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
            """
            
            current_prompt = observation_template.format(tool_result_json=json.dumps(tool_result))

    except Exception as e:
        error_message = f"An error occurred during reasoning: {str(e)}"
        logging.exception(error_message)
        socketio.emit('log_message', {'type': 'error', 'data': error_message}, to=session_id)
    finally:
        logging.info("Reasoning Loop Ended")