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
    pattern = re.compile(r"START (@@\\w+).*?END \\1", re.DOTALL)
    return pattern.sub("", text)

def parse_agent_response(response_text: str) -> (str | None, dict | None, bool):
    """
    Parses a potentially messy agent response to separate prose from a valid command JSON.
    """
    
    def is_prose_effectively_empty(prose_string: str | None) -> bool:
        if not prose_string:
            return True
        timestamp_pattern = r'^\\[\\d{4}-\\d{2}-\\d{2} \\d{2}:\\d{2}:\\d{2}\\]\\s*'
        prose_without_timestamp = re.sub(timestamp_pattern, '', prose_string.strip())
        return prose_without_timestamp.strip() == ""

    sanitized_text = _mask_payloads(response_text)

    full_match_block, command_json_str = _extract_json_with_fences(sanitized_text)
    if not (full_match_block and command_json_str):
        full_match_block, command_json_str = _extract_json_with_brace_counting(sanitized_text)
        
    if command_json_str:
        try:
            command_json = json.loads(command_json_str)
        except json.JSONDecodeError:
            command_json_str = _repair_json(command_json_str)
            try:
                command_json = json.loads(command_json_str)
            except json.JSONDecodeError:
                prose_is_empty = is_prose_effectively_empty(response_text)
                return _clean_prose(response_text), None, prose_is_empty

        final_prose = response_text.replace(full_match_block, "", 1).strip()
        prose_is_empty = is_prose_effectively_empty(final_prose)
        return _clean_prose(final_prose), command_json, prose_is_empty

    prose_is_empty = is_prose_effectively_empty(response_text)
    return _clean_prose(response_text), None, prose_is_empty

def _extract_json_with_fences(text: str) -> (str | None, str | None):
    pattern = r"(```json\\s*\\n?({.*?})\\s*\\n?```)"
    matches = list(re.finditer(pattern, text, re.DOTALL))
    if not matches:
        return None, None
    largest_match = max(matches, key=lambda m: len(m.group(2)))
    return largest_match.group(1), largest_match.group(2)

def _extract_json_with_brace_counting(text: str) -> (str | None, str | None):
    best_json_candidate = None
    start_indices = [m.start() for m in re.finditer('{', text)]
    for start_index in start_indices:
        open_braces = 0
        in_string = False
        for i, char in enumerate(text[start_index:]):
            if char == '"' and (i == 0 or text[start_index + i - 1] != '\\\\'):
                in_string = not in_string
            if not in_string:
                if char == '{':
                    open_braces += 1
                elif char == '}':
                    open_braces -= 1
            if open_braces == 0:
                potential_json = text[start_index : start_index + i + 1]
                try:
                    repaired_potential = _repair_json(potential_json)
                    json.loads(repaired_potential)
                    if not best_json_candidate or len(repaired_potential) > len(best_json_candidate):
                        best_json_candidate = repaired_potential
                except json.JSONDecodeError:
                    continue
    return best_json_candidate, best_json_candidate

def _repair_json(s: str) -> str:
    s_before_loop = s
    for _ in range(1000):
        try:
            json.loads(s)
            return s
        except json.JSONDecodeError as e:
            error_fixed = False
            if "Invalid control character at" in e.msg:
                char_pos = e.pos
                char_to_escape = s[char_pos]
                escape_map = {'\\n': '\\\\n', '\\r': '\\\\r', '\\t': '\\\\t'}
                if char_to_escape in escape_map:
                    s = s[:char_pos] + escape_map[char_to_escape] + s[char_pos+1:]
                    error_fixed = True
            elif "Expecting" in e.msg or "Unterminated string" in e.msg:
                quote_pos = s.rfind('"', 0, e.pos)
                if quote_pos != -1:
                    p = quote_pos - 1
                    slashes = 0
                    while p >= 0 and s[p] == '\\\\':
                        slashes += 1
                        p -= 1
                    if slashes % 2 == 0:
                        s = s[:quote_pos] + '\\\\' + s[quote_pos:]
                        error_fixed = True
            if not error_fixed:
                return s_before_loop
    return s

def _clean_prose(prose: str | None) -> str | None:
    if prose:
        return prose.strip()
    return None

def _handle_payloads(prose, command_json):
    if not command_json or 'parameters' not in command_json or not prose:
        return prose, command_json
    
    params = command_json['parameters']
    placeholders_to_process = [(k, v) for k, v in params.items() if isinstance(v, str) and v.startswith('@@')]

    for key, placeholder in placeholders_to_process:
        start_marker = f"START {placeholder}"
        end_marker = f"END {placeholder}"
        start_index = prose.find(start_marker)
        if start_index != -1:
            end_index = prose.find(end_marker, start_index)
            if end_index != -1:
                content_start = start_index + len(start_marker)
                payload_content = prose[content_start:end_index].strip()
                params[key] = payload_content
                prose = prose.replace(prose[start_index:end_index + len(end_marker)], "").strip()
                logging.info(f"Successfully extracted payload for '{placeholder}'.")
    return prose, command_json

def _emit_agent_message(socketio, session_id, message_type, content):
    if content and content.strip():
        socketio.emit('log_message', {'type': message_type, 'data': content}, to=session_id)

def _process_and_render_model_turn(socketio, session_id, timestamped_response_text, is_live=False):
    prose, command_json, prose_is_empty = parse_agent_response(timestamped_response_text)
    prose, command_json = _handle_payloads(prose, command_json)

    if prose and command_json: 
        command_json['attachment'] = prose

    if not command_json:
        logging.warning("Could not decode JSON from model response. Treating as plain text.")
        command_json = {"action": "respond", "parameters": {"response": timestamped_response_text}}

    action = command_json.get("action")
    
    if action in ['respond', 'task_complete']:
        prose_text = command_json.get('attachment', '') or ""
        response_param_text = command_json.get('parameters', {}).get('response', '') or ""
        final_message = prose_text if len(prose_text.strip()) > len(response_param_text.strip()) else response_param_text
        if not prose_is_empty:
            _emit_agent_message(socketio, session_id, 'final_answer', final_message)
    elif action == 'request_confirmation':
        if prose:
            _emit_agent_message(socketio, session_id, 'info', prose)
        prompt = command_json.get('parameters', {}).get('prompt', 'Are you sure?')
        message_type = 'system_confirm' if is_live else 'system_confirm_replayed'
        socketio.emit('request_user_confirmation' if is_live else 'log_message', {'prompt': prompt, 'type': message_type}, to=session_id)
    elif prose and not prose_is_empty:
        _emit_agent_message(socketio, session_id, 'info', prose)
        
    return command_json

def replay_history_for_client(socketio, session_id, session_name, history):
    try:
        socketio.emit('clear_chat_history', to=session_id)
        socketio.sleep(0.1)
        for item in history:
            role = item.get('role')
            raw_text = (item.get('parts', [{}])[0] or {}).get('text', '')
            if not raw_text or not raw_text.strip():
                continue
            if role == 'user':
                socketio.emit('log_message', {'type': 'user', 'data': raw_text}, to=session_id)
            elif role == 'model':
                _process_and_render_model_turn(socketio, session_id, raw_text, is_live=False)
            socketio.sleep(0.01)
    except Exception as e:
        logging.error(f"Error during history replay for session {session_name}: {e}")
        socketio.emit('log_message', {'type': 'error', 'data': f"Failed to replay history: {e}"}, to=session_id)

def execute_reasoning_loop(socketio, initial_session_data, initial_prompt, session_id, chat_sessions, model, api_stats):
    loop_id = str(uuid.uuid4())
    try:
        current_prompt = initial_prompt
        destruction_confirmed = False

        for i in range(ABSOLUTE_MAX_ITERATIONS_REASONING_LOOP):
            socketio.sleep(0)
            
            # --- NEW: Re-fetch session data on each loop to ensure context is fresh ---
            session_data = chat_sessions.get(session_id)
            if not session_data:
                logging.error(f"Session data for {session_id} disappeared mid-loop.")
                socketio.emit('log_message', {'type': 'error', 'data': "Session data lost. Please refresh."}, to=session_id)
                return
                
            chat = session_data.get('chat')
            memory = session_data.get('memory')

            if not chat or not memory:
                error_message = f"Could not find chat or memory object for session {session_id}."
                logging.error(error_message)
                socketio.emit('log_message', {'type': 'error', 'data': error_message}, to=session_id)
                return

            final_prompt = (
                f"This is iteration {i+1} of {NOMINAL_MAX_ITERATIONS_REASONING_LOOP} of the reasoning loop.\\n"
                f"You MUST issue a resonse to the user on or before the final iteration.\\n"
                f"The prompt for the current iteration is below:\\n\\n"
                f"{current_prompt}"
            )

            memory.add_turn("user", current_prompt)
            response = tpool.execute(chat.send_message, final_prompt)
            response_text = response.text
            
            if not re.match(r'^\\[\\d{4}-\\d{2}-\\d{2} \\d{2}:\\d{2}:\\d{2}\\]', response_text):
                timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                response_text = f"[{timestamp}] {response_text}"

            memory.add_turn("model", response_text)
            command_json = _process_and_render_model_turn(socketio, session_id, response_text, is_live=True)
            action = command_json.get("action")

            if i >= NOMINAL_MAX_ITERATIONS_REASONING_LOOP and not action == "respond":
                current_prompt = "WARNING: You have exceeded the maximum number of allowed reasoning loop iterations. You MUST use the `respond` command to issue a response to the user and terminate this reasoning loop."
                continue

            if action in ['respond', 'task_complete']:
                logging.info(f"Agent has issued a response. Terminating reasoning loop for session {session_id}.")
                return

            destructive_actions = ['delete_file', 'delete_session']
            if action in destructive_actions and not destruction_confirmed:
                err_msg = f"Action '{action}' is destructive and requires user confirmation. I must use 'request_confirmation' first."
                logging.warning(err_msg)
                error_payload = {'status': 'error', 'message': err_msg}
                current_prompt = f"Tool Result: {json.dumps(error_payload)}"
                destruction_confirmed = False
                continue
            
            if action == 'request_confirmation':
                confirmation_event = Event()
                confirmation_events[session_id] = confirmation_event
                user_response = confirmation_event.wait()
                confirmation_events.pop(session_id, None)
                destruction_confirmed = user_response == 'yes'
                current_prompt = f"USER_CONFIRMATION: '{user_response}'"
                continue

            tool_result = execute_tool_command(command_json, socketio, session_id, chat_sessions, model, loop_id)            
            destruction_confirmed = False

            log_message = tool_result.get('message', f"Tool '{action}' executed successfully.")
            socketio.emit('tool_log', {'data': f"[{log_message}]"}, to=session_id)

            if action == "load_session":
                return 

            current_prompt = f"Tool Result: {json.dumps(tool_result)}"

    except Exception as e:
        error_message = f"An error occurred during reasoning: {str(e)}"
        logging.exception(error_message)
        socketio.emit('log_message', {'type': 'error', 'data': error_message}, to=session_id)
    finally:
        logging.info("Reasoning Loop Ended")