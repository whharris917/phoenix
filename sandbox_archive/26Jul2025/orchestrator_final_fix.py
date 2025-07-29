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
    pattern = re.compile(r"START (@@\w+).*?END \1", re.DOTALL)
    return pattern.sub("", text)

def parse_agent_response(response_text: str) -> (str | None, dict | None, bool):
    """
    Parses a potentially messy agent response to separate prose from a valid command JSON.
    """
    def is_prose_effectively_empty(prose_string: str | None) -> bool:
        if not prose_string:
            return True
        timestamp_pattern = r'^\[\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\]\s*'
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
            try:
                command_json_str_repaired = _repair_json(command_json_str)
                command_json = json.loads(command_json_str_repaired)
            except json.JSONDecodeError:
                prose_is_empty = is_prose_effectively_empty(response_text)
                return _clean_prose(response_text), None, prose_is_empty
        
        # Use the original match block for replacement to preserve payloads
        final_prose = response_text.replace(full_match_block, "", 1).strip()
        prose_is_empty = is_prose_effectively_empty(final_prose)
        return _clean_prose(final_prose), command_json, prose_is_empty

    prose_is_empty = is_prose_effectively_empty(response_text)
    return _clean_prose(response_text), None, prose_is_empty


def _extract_json_with_fences(text: str) -> (str | None, str | None):
    """
    Extracts the largest JSON block and its full enclosing ``` fences.
    """
    pattern = r"(```json\s*\n?({.*?})\s*\n?```)"
    matches = list(re.finditer(pattern, text, re.DOTALL))
    if not matches:
        return None, None
    largest_match = max(matches, key=lambda m: len(m.group(2)))
    return largest_match.group(1), largest_match.group(2)


def _extract_json_with_brace_counting(text: str) -> (str | None, str | None):
    """
    Finds the largest valid JSON object in a string by counting braces.
    """
    best_json_candidate = None
    start_indices = [m.start() for m in re.finditer('{', text)]
    for start_index in start_indices:
        open_braces = 0
        in_string = False
        for i, char in enumerate(text[start_index:]):
            if char == '\"' and (i == 0 or text[start_index + i - 1] != '\\'):
                in_string = not in_string
            if not in_string:
                if char == '{': open_braces += 1
                elif char == '}': open_braces -= 1
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
    """
    Attempts to repair a malformed JSON string.
    """
    s_before_loop = s
    max_iterations = 1000
    for _ in range(max_iterations):
        try:
            json.loads(s)
            return s
        except json.JSONDecodeError as e:
            error_fixed = False
            if "Invalid control character at" in e.msg:
                char_pos = e.pos
                char_to_escape = s[char_pos]
                escape_map = {'\n': '\\n', '\r': '\\r', '\t': '\\t'}
                if char_to_escape in escape_map:
                    s = s[:char_pos] + escape_map[char_to_escape] + s[char_pos+1:]
                    error_fixed = True
            elif "Expecting" in e.msg or "Unterminated string" in e.msg:
                quote_pos = s.rfind('"', 0, e.pos)
                if quote_pos != -1:
                    p = quote_pos - 1
                    slashes = 0
                    while p >= 0 and s[p] == '\\':
                        slashes += 1
                        p -= 1
                    if slashes % 2 == 0:
                        s = s[:quote_pos] + '\\' + s[quote_pos:]
                        error_fixed = True
            if not error_fixed:
                return s_before_loop
    return s

def _clean_prose(prose: str | None) -> str | None:
    if prose:
        return prose.strip()
    return None

def _handle_payloads(prose, command_json):
    placeholders_found = []
    if not command_json or 'parameters' not in command_json or not prose:
        return prose, command_json, placeholders_found

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
                placeholders_found.append(placeholder)
    
    if placeholders_found:
        temp_prose = prose
        for placeholder in placeholders_found:
            pattern = re.compile(f"START {re.escape(placeholder)}.*?END {re.escape(placeholder)}", re.DOTALL)
            temp_prose = pattern.sub('', temp_prose)
        prose = temp_prose.strip()

    return prose, command_json, placeholders_found


def replay_history_for_client(socketio, session_id, session_name, history):
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
                
                if not is_tool_result:
                    try:
                        tool_result = json.loads(raw_text)
                        if isinstance(tool_result, dict) and 'status' in tool_result:
                            log_message = tool_result.get('message', 'Tool action completed.')
                            socketio.emit('tool_log', {'data': f"[{log_message}]"}, to=session_id)
                            is_tool_result = True
                    except (json.JSONDecodeError, TypeError):
                        pass
                
                if is_tool_result:
                    continue
                
                if not raw_text.startswith('USER_CONFIRMATION:'):
                    socketio.emit('log_message', {'type': 'user', 'data': raw_text}, to=session_id)
            
            elif role == 'model':
                prose, command_json, prose_is_empty = parse_agent_response(raw_text)
                if prose_is_empty and not command_json:
                    continue
                
                cleaned_prose, _, _ = _handle_payloads(prose, command_json)
                final_message_for_display = ""
                
                if command_json:
                    action = command_json.get('action')
                    if action in ['respond', 'task_complete']:
                        response_param_text = command_json.get('parameters', {}).get('response', '') or ""
                        prose_text = cleaned_prose or ""
                        final_message_for_display = prose_text if len(prose_text.strip()) > len(response_param_text.strip()) else response_param_text
                elif cleaned_prose:
                    final_message_for_display = cleaned_prose

                if final_message_for_display:
                    socketio.emit('log_message', {'type': 'final_answer', 'data': final_message_for_display}, to=session_id)
                elif cleaned_prose:
                    socketio.emit('log_message', {'type': 'info', 'data': cleaned_prose}, to=session_id)
                
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
    
    audit_log.log_event("Reasoning Loop Started", session_id=session_id, session_name=get_current_session_name(), loop_id=loop_id, source="Orchestrator", details={"initial_prompt": initial_prompt})

    try:
        current_prompt = initial_prompt
        destruction_confirmed = False

        chat = session_data.get('chat')
        memory = session_data.get('memory')
        if not chat or not memory:
            socketio.emit('log_message', {'type': 'error', 'data': 'Critical error: Chat or Memory session object not found.'}, to=session_id)
            return

        observation_template = "Tool Result: {tool_result_json}"

        for i in range(100):
            socketio.sleep(0)
            memory.add_turn("user", current_prompt)

            response = tpool.execute(chat.send_message, current_prompt)
            
            if response.usage_metadata:
                api_stats['total_calls'] += 1
                api_stats['total_prompt_tokens'] += response.usage_metadata.prompt_token_count
                api_stats['total_completion_tokens'] += response.usage_metadata.candidates_token_count
                socketio.emit('api_usage_update', api_stats)
            
            response_text = response.text
            if not re.match(r'^\[\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\]', response_text):
                timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                response_text = f"[{timestamp}] {response_text}"

            memory.add_turn("model", response_text)

            prose, command_json, prose_is_empty = parse_agent_response(response_text)
            prose, command_json, _ = _handle_payloads(prose, command_json)
            
            if prose and command_json:    
                command_json['attachment'] = prose   

            if not command_json:
                command_json = {"action": "respond", "parameters": {"response": response_text}}

            action = command_json.get("action")
            
            # --- UNIFIED MESSAGE HANDLING LOGIC ---
            final_message_to_user = ""
            # Determine if it's a final message action
            if action in ['respond', 'task_complete']:
                prose_text = command_json.get('attachment', '') or ""
                response_param_text = command_json.get('parameters', {}).get('response', '') or ""
                final_message_to_user = prose_text if len(prose_text.strip()) > len(response_param_text.strip()) else response_param_text

            # If we have a final message, send it and terminate the loop.
            if final_message_to_user:
                if final_message_to_user.strip() and not prose_is_empty:
                    socketio.emit('log_message', {'type': 'final_answer', 'data': final_message_to_user}, to=session_id)
                if action == 'task_complete':
                    logging.info("Agent initiated task_complete.")
                return # Exit loop for both respond and task_complete

            # If not a final message, it must be a tool-related action.
            # Handle destructive checks and confirmations first.
            destructive_actions = ['delete_file', 'delete_session']
            if action in destructive_actions and not destruction_confirmed:
                err_msg = f"Action '{action}' is destructive and requires user confirmation. I must use 'request_confirmation' first."
                current_prompt = observation_template.format(tool_result_json=json.dumps({'status': 'error', 'message': err_msg}))
                continue

            if action == 'request_confirmation':
                prompt_text = command_json.get('parameters', {}).get('prompt', 'Are you sure?')
                if command_json.get('attachment'):
                    prose_text = command_json.get('attachment', '')
                    if prose_text and prose_text.strip() and not prose_is_empty:
                        socketio.emit('log_message', {'type': 'info', 'data': prose_text}, to=session_id)

                confirmation_event = Event()
                confirmation_events[session_id] = confirmation_event
                socketio.emit('request_user_confirmation', {'prompt': prompt_text}, to=session_id)
                user_response = confirmation_event.wait()
                confirmation_events.pop(session_id, None)
                destruction_confirmed = (user_response == 'yes')
                current_prompt = f"USER_CONFIRMATION: '{user_response}'"
                continue

            # --- TOOL EXECUTION AND RE-ORDERED RESPONSE ---
            tool_result = execute_tool_command(command_json, socketio, session_id, chat_sessions, model, loop_id)
            destruction_confirmed = False

            # STEP 1: Log tool result
            log_message = tool_result.get('message', f"Tool '{action}' executed.")
            socketio.emit('tool_log', {'data': f"[{log_message}]"}, to=session_id)

            if action == "load_session":
                return

            # STEP 2: Send agent's explanatory prose
            if command_json.get('attachment'):
                prose_text = command_json.get('attachment', '')
                if prose_text and prose_text.strip() and not prose_is_empty:
                    socketio.emit('log_message', {'type': 'info', 'data': prose_text}, to=session_id)

            # STEP 3: Request confirmation to proceed
            prompt_text = "Tool execution complete. May I proceed?"
            confirmation_event = Event()
            confirmation_events[session_id] = confirmation_event
            socketio.emit('request_user_confirmation', {'prompt': prompt_text}, to=session_id)
            user_response = confirmation_event.wait()
            confirmation_events.pop(session_id, None)

            if user_response != 'yes':
                logging.info(f"User halted execution. Ending loop.")
                socketio.emit('log_message', {'type': 'info', 'data': "Execution halted by user."}, to=session_id)
                break 
            
            current_prompt = observation_template.format(tool_result_json=json.dumps(tool_result))

    except Exception as e:
        logging.exception("An error occurred in the reasoning loop.")
        socketio.emit('log_message', {'type': 'error', 'data': f"An error occurred during reasoning: {str(e)}"}, to=session_id)
    finally:
        audit_log.log_event("Reasoning Loop Ended", session_id=session_id, session_name=get_current_session_name(), loop_id=loop_id, source="Orchestrator")