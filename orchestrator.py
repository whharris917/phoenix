import json
import logging
from eventlet import tpool
from eventlet.event import Event
from tool_agent import execute_tool_command
from audit_logger import audit_log
import uuid
import debugpy

confirmation_events = {}

import json
import re

def parse_agent_response(response_text: str) -> (str | None, dict | None):
    """
    Parses a potentially messy agent response to separate prose from a valid command JSON.

    This function is designed to handle "mixed messages" containing both natural
    language text (prose) and a command in JSON format. It addresses several
    failure modes, including missing JSON fences, malformed JSON, and prose
    that might be mistaken for JSON.

    Args:
        response_text: The raw string response from the agent.

    Returns:
        A tuple containing two elements:
        - The cleaned prose string (or None if no prose is found).
        - The parsed command JSON as a Python dictionary (or None if no valid JSON is found).
    """
    prose, command_json_str = _extract_json_with_fences(response_text)
    if command_json_str:
        # If fences are found, we prioritize that and attempt to parse it.
        try:
            # First, try to load it as is.
            # If the agent provides a valid JSON with escaped newlines, this will work.
            command_json = json.loads(command_json_str)
            return _clean_prose(prose), command_json
        except json.JSONDecodeError:
            # If it fails, it might be malformed. Let's try to repair it.
            repaired_json_str = _repair_json(command_json_str)
            try:
                command_json = json.loads(repaired_json_str)
                return _clean_prose(prose), command_json
            except json.JSONDecodeError:
                # If repair fails, we fall through to brace counting on the whole text.
                pass

    # If no fences were found or the fenced content was irreparable, try brace counting.
    prose, command_json_str = _extract_json_with_brace_counting(response_text)
    if command_json_str:
        try:
            command_json = json.loads(command_json_str)
            return _clean_prose(prose), command_json
        except json.JSONDecodeError:
            repaired_json_str = _repair_json(command_json_str)
            try:
                command_json = json.loads(repaired_json_str)
                # The prose here is what's left after extracting the JSON
                return _clean_prose(prose), command_json
            except json.JSONDecodeError as e:
                print(f"Failed to parse JSON even after repair: {e}")
                # If all attempts fail, return the original text as prose.
                return _clean_prose(response_text), None

    # If no JSON of any kind is found, the whole response is prose.
    return _clean_prose(response_text), None

def _extract_json_with_fences(text: str) -> (str, str | None):
    """
    Extracts the largest JSON block enclosed in ```json ... ``` fences.
    """
    matches = list(re.finditer(r"```json\s*\n?({.*?})\s*\n?```", text, re.DOTALL))
    if not matches:
        return text, None
    largest_json_str = ""
    largest_match_obj = None

    # Find the largest JSON block among all fenced blocks
    for match in matches:
        json_str = match.group(1)
        if len(json_str) > len(largest_json_str):
            largest_json_str = json_str
            largest_match_obj = match
    if largest_match_obj:
        # The prose is everything outside the largest matched block.
        prose = text.replace(largest_match_obj.group(0), "").strip()
        return prose, largest_json_str
    return text, None

def _extract_json_with_brace_counting(text: str) -> (str, str | None):
    """
    Finds the largest valid JSON object in a string by counting braces.
    This is a fallback for when JSON is not properly fenced.
    """
    best_json_candidate = None
    best_candidate_prose = text
    
    # Find all potential start indices for a JSON object
    start_indices = [m.start() for m in re.finditer('{', text)]
    for start_index in start_indices:
        open_braces = 0
        in_string = False
        # We must check every possible end point for each start point
        for i, char in enumerate(text[start_index:]):
            if char == '"' and (i == 0 or text[start_index + i - 1] != '\\'):
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
    return best_candidate_prose, best_json_candidate

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

def replay_history_for_client(socketio, session_id, session_name, history):
    """
    Parses the raw chat history and emits granular rendering events to the client,
    acting as a 'dry run' of the orchestrator's live logic.
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
                if raw_text.startswith(('TOOL_RESULT:', 'OBSERVATION:', 'Tool Result:')):
                    try:
                        json_str = raw_text[raw_text.find('{'):]
                        tool_result = json.loads(json_str)
                        log_message = tool_result.get('message', 'Tool action completed.')
                        socketio.emit('tool_log', {'data': f"[{log_message}]"}, to=session_id)
                    except (json.JSONDecodeError, IndexError):
                        socketio.emit('tool_log', {'data': f"[{raw_text}]"}, to=session_id)
                    continue
                elif not raw_text.startswith('USER_CONFIRMATION:'):
                    socketio.emit('log_message', {'type': 'user', 'data': raw_text}, to=session_id)
            
            elif role == 'model':
                prose, command_json = parse_agent_response(raw_text)

                if prose and not command_json:
                    socketio.emit('log_message', {'type': 'final_answer', 'data': prose}, to=session_id)
                    continue

                if prose:
                    socketio.emit('log_message', {'type': 'info', 'data': prose}, to=session_id)

                if command_json:
                    action = command_json.get('action')
                    params = command_json.get('parameters', {})

                    if action in ['respond', 'task_complete']:
                        response = params.get('response', '').strip()
                        if response:
                            socketio.emit('log_message', {'type': 'final_answer', 'data': response}, to=session_id)
                    elif action == 'request_confirmation':
                        prompt = params.get('prompt')
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

    audit_log.log_event("Reasoning Loop Started", session_id=session_id, session_name=get_current_session_name(), loop_id=loop_id, source="Orchestrator", destination="Orchestrator", details={"initial_prompt": initial_prompt})
    
    try:
        current_prompt = initial_prompt
        destruction_confirmed = False

        if not isinstance(session_data, dict):
            logging.error(f"Session data for {session_id} is not a dictionary.")
            return

        chat = session_data.get('chat')
        memory = session_data.get('memory')

        if not chat or not memory:
            logging.error(f"Could not find chat or memory object for session {session_id}")
            socketio.emit('log_message', {'type': 'error', 'data': 'Critical error: Chat or Memory session object not found.'}, to=session_id)
            return

        observation_template = "Tool Result: {tool_result_json}"

        for i in range(15):
            socketio.sleep(0)
            
            retrieved_context = memory.get_context_for_prompt(current_prompt)

            final_prompt = current_prompt
            if retrieved_context:
                context_str = "\n".join(retrieved_context)
                final_prompt = (
                    "CONTEXT FROM PAST CONVERSATIONS:\n"
                    f"{context_str}\n\n"
                    "Based on the above context, please respond to the following prompt:\n"
                    f"{current_prompt}"
                )
                logging.info(f"Augmented prompt with {len(retrieved_context)} documents from memory.")

            memory.add_turn("user", current_prompt)

            audit_log.log_event("Gemini API Call Sent", session_id=session_id, session_name=get_current_session_name(), loop_id=loop_id, source="Orchestrator", destination="Model", observers=["Orchestrator", "Model"], details={"prompt": final_prompt})
            response = tpool.execute(chat.send_message, final_prompt)
            audit_log.log_event("Gemini API Response Received", session_id=session_id, session_name=get_current_session_name(), loop_id=loop_id, source="Model", destination="Orchestrator", observers=["Orchestrator", "Model"], details={"response_text": response.text})

            if response.usage_metadata:
                api_stats['total_calls'] += 1
                api_stats['total_prompt_tokens'] += response.usage_metadata.prompt_token_count
                api_stats['total_completion_tokens'] += response.usage_metadata.candidates_token_count
                socketio.emit('api_usage_update', api_stats)
            
            response_text = response.text
            memory.add_turn("model", response_text)

            prose, command_json = parse_agent_response(response_text)

            if command_json and prose:
                command_json['attachment'] = prose
                audit_log.log_event("Socket.IO Emit: log_message", session_id=session_id, session_name=get_current_session_name(), loop_id=loop_id, source="Orchestrator", destination="Client", observers=["User"], details={'type': 'info', 'data': prose})
                socketio.emit('log_message', {'type': 'info', 'data': prose}, to=session_id)

            if not command_json:
                # If no JSON was found or parsing/healing failed, treat the whole response as prose.
                logging.warning(f"Could not decode JSON from model response. Treating as plain text.")
                final_prose = prose or response_text # Use prose if available, otherwise full text
                command_json = {"action": "respond", "parameters": {"response": final_prose}}

            # --- END OF NEW PARSING LOGIC ---

            action = command_json.get("action")

            if action == 'respond':
                response_to_user = command_json.get('parameters', {}).get('response', '')
                if response_to_user and response_to_user.strip():
                    audit_log.log_event("Socket.IO Emit: log_message", session_id=session_id, session_name=get_current_session_name(), loop_id=loop_id, source="Orchestrator", destination="Client", observers=["User", "Orchestrator"], details={'type': 'final_answer', 'data': response_to_user})
                    socketio.emit('log_message', {'type': 'final_answer', 'data': response_to_user}, to=session_id)
                return
            
            if action == 'task_complete':
                final_response = command_json.get('parameters', {}).get('response')
                if final_response and final_response.strip():
                    audit_log.log_event("Socket.IO Emit: log_message", session_id=session_id, session_name=get_current_session_name(), loop_id=loop_id, source="Orchestrator", destination="Client", observers=["User", "Orchestrator"], details={'type': 'final_answer', 'data': final_response})
                    socketio.emit('log_message', {'type': 'final_answer', 'data': final_response}, to=session_id)
                logging.info(f"Agent initiated task_complete. Ending loop for session {session_id}.")
                return

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

            audit_log.log_event("Tool Agent Call Sent", session_id=session_id, session_name=get_current_session_name(), loop_id=loop_id, source="Orchestrator", destination="Tool Agent", observers=["Orchestrator", "Tool Agent"], details=command_json)
            tool_result = execute_tool_command(command_json, socketio, session_id, chat_sessions, model)            
            audit_log.log_event("Tool Agent Execution Finished", session_id=session_id, session_name=get_current_session_name(), loop_id=loop_id, source="Tool Agent", destination="Orchestrator", observers=["Orchestrator", "Tool Agent"], details=tool_result)

            destruction_confirmed = False

            if tool_result.get('status') == 'success':
                log_message = tool_result.get('message', f"Tool '{action}' executed successfully.")
                audit_log.log_event("Socket.IO Emit: tool_log", session_id=session_id, session_name=get_current_session_name(), loop_id=loop_id, source="Orchestrator", destination="Client", observers=["User", "Orchestrator"], details={'data': f"[{log_message}]"})
                socketio.emit('tool_log', {'data': f"[{log_message}]"}, to=session_id)
                if action == "load_session":
                    return
            else:
                pass

            current_prompt = observation_template.format(tool_result_json=json.dumps(tool_result))

    except Exception as e:
        logging.exception("An error occurred in the reasoning loop.")
        socketio.emit('log_message', {'type': 'error', 'data': f"An error occurred during reasoning: {str(e)}"}, to=session_id)
    finally:
        audit_log.log_event("Reasoning Loop Ended", session_id=session_id, session_name=get_current_session_name(), loop_id=loop_id, source="Orchestrator", destination="Orchestrator", observers=["Orchestrator"])
