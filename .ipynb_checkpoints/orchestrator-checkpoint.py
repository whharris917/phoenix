import json
import logging
from eventlet import tpool
from eventlet.event import Event
from tool_agent import execute_tool_command
from audit_logger import audit_log
import uuid
import debugpy

confirmation_events = {}

def find_json_block(text):

    # First, try to find a markdown-style JSON block
    start_marker = '```json'
    end_marker = '```'
    start_index = text.find(start_marker)

    if start_index != -1:
        end_index = text.find(end_marker, start_index + len(start_marker))
        if end_index != -1:
            # Extract the content between the markers
            json_content_start = start_index + len(start_marker)
            return json_content_start, end_index

    # If markdown block is not found, fall back to brace counting from the end
    end_brace_index = text.rfind('}')
    if end_brace_index == -1:
        return None, None

    brace_count = 1
    start_brace_index = -1

    for i in range(end_brace_index - 1, -1, -1):
        if text[i] == '}': brace_count += 1
        elif text[i] == '{': brace_count -= 1
        if brace_count == 0:
            start_brace_index = i
            break

    if start_brace_index == -1:
        return None, None

    return start_brace_index, end_brace_index + 1

def find_and_extract_json_with_prose(text):
    """
    Finds a JSON block, prioritizing markdown fences, and separates it from surrounding text.
    Returns a tuple: (json_string, prose_string)
    """
    # Prioritize finding a markdown-fenced JSON block
    start_marker = '```json'
    end_marker = '```'
    start_pos = text.find(start_marker)

    if start_pos != -1:
        end_pos = text.find(end_marker, start_pos + len(start_marker))
        if end_pos != -1:
            json_str = text[start_pos + len(start_marker):end_pos].strip()
            prose_str = (text[:start_pos].strip() + ' ' + text[end_pos + len(end_marker):].strip()).strip()
            return json_str, prose_str

    # Fallback to brace-counting from the end if no markdown block is found
    end_brace_pos = text.rfind('}')
    if end_brace_pos == -1:
        return None, text # No JSON found, return original text as prose

    brace_count = 1
    start_brace_pos = -1
    for i in range(end_brace_pos - 1, -1, -1):
        if text[i] == '}': brace_count += 1
        elif text[i] == '{': brace_count -= 1
        if brace_count == 0:
            start_brace_pos = i
            break

    if start_brace_pos != -1:
        json_str = text[start_brace_pos:end_brace_pos + 1]
        prose_str = text[:start_brace_pos].strip()
        return json_str, prose_str

    return None, text # No JSON found, return original text as prose

def replay_history_for_client(socketio, session_id, session_name, history):
    """
    Parses the raw chat history and emits granular rendering events to the client,
    acting as a 'dry run' of the orchestrator's live logic.
    """
    audit_log.log_event("History Replay Started", session_id=session_id, session_name=session_name, source="Orchestrator", destination="Client", details=f"Replaying {len(history)} turns.")
    socketio.emit('clear_chat_history', to=session_id)
    socketio.sleep(0.1)

    for item in history:
        role = item.get('role')
        raw_text = ""
        if item.get('parts') and isinstance(item['parts'], list) and len(item['parts']) > 0:
            part = item['parts'][0]
            if isinstance(part, dict) and 'text' in part:
                raw_text = part.get('text', '')
            elif isinstance(part, str):
                raw_text = part
        
        if not raw_text or not raw_text.strip():
            continue

        if role == 'user':
            if raw_text.startswith(('TOOL_RESULT:', 'OBSERVATION:')):
                try:
                    json_str = raw_text[raw_text.find('{'):]
                    tool_result = json.loads(json_str)
                    log_message = tool_result.get('message', f"Tool executed.")
                    socketio.emit('tool_log', {'data': f"[{log_message}]"}, to=session_id)
                except json.JSONDecodeError:
                    socketio.emit('tool_log', {'data': "[Tool action completed]"}, to=session_id)
            elif not raw_text.startswith('USER_CONFIRMATION:'):
                socketio.emit('log_message', {'type': 'user', 'data': raw_text}, to=session_id)
        
        elif role == 'model':
            start_index, end_index = find_json_block(raw_text)
            if start_index is not None:
                """
                attachment = raw_text[:start_index].strip().strip('```json').strip('`')
                if attachment:
                    socketio.emit('log_message', {'type': 'info', 'data': attachment}, to=session_id)
                """
                
                json_str = raw_text[start_index:end_index]
                # The rest of the string is the attachment
                attachment = (raw_text[:start_index].strip().replace('```json', '') + raw_text[end_index:].strip().replace('```', '')).strip()
                try:
                    command = json.loads(json_str)
                    action = command.get('action')
                    params = command.get('parameters', {})
                    if action in ['respond', 'task_complete'] and params.get('response') and params.get('response').strip():
                        socketio.emit('log_message', {'type': 'final_answer', 'data': params['response']}, to=session_id)
                    elif action == 'request_confirmation' and params.get('prompt'):
                        socketio.emit('log_message', {'type': 'system_confirm', 'data': params['prompt']}, to=session_id)
                except json.JSONDecodeError:
                    if raw_text and raw_text.strip():
                        socketio.emit('log_message', {'type': 'final_answer', 'data': raw_text}, to=session_id)
            else:
                if raw_text and raw_text.strip():
                    socketio.emit('log_message', {'type': 'final_answer', 'data': raw_text}, to=session_id)
        socketio.sleep(0.01)

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

            """
            try:
                start_index, end_index = find_json_block(response_text)
                
                if start_index is not None:
                    json_str = response_text[start_index:end_index]
                    attachment_text = response_text[:start_index].strip().strip('```json').strip('`')
                    command_json = json.loads(json_str)

                    if attachment_text:
                        command_json['attachment'] = attachment_text
                        audit_log.log_event("Socket.IO Emit: log_message", session_id=session_id, session_name=get_current_session_name(), loop_id=loop_id, source="Orchestrator", destination="Client", observers=["User"], details={'type': 'info', 'data': attachment_text})
                        socketio.emit('log_message', {'type': 'info', 'data': attachment_text}, to=session_id)
                else:
                    command_json = {"action": "respond", "parameters": {"response": response_text}}

            except json.JSONDecodeError:
                logging.warning(f"Could not decode JSON from model response. Treating as plain text. Response: {response_text}")
                command_json = {"action": "respond", "parameters": {"response": response_text}}
            """

            """
            command_json = None
            start_index, end_index = find_json_block(response_text)
            
            if start_index is not None:
                json_str = response_text[start_index:end_index]
                attachment_text = response_text[:start_index].strip().strip('```json').strip('`')
                
                # --- NEW: Self-healing JSON repair loop ---
                max_repair_attempts = 50
                for attempt in range(max_repair_attempts):
                    try:
                        command_json = json.loads(json_str)
                        if attempt > 0:
                            logging.info(f"Successfully repaired JSON after {attempt + 1} attempts.")
                        break  # Exit loop on success

                    except json.JSONDecodeError as e:
                        # Heuristic: The most common error is an unescaped double quote inside a string value.
                        # This causes the parser to end the string prematurely and fail on the next character.
                        # The error position `e.pos` is where the parser failed, so the problematic quote is just before it.
                        
                        # Let's find the last double-quote character at or before the error position.
                        offending_quote_pos = json_str.rfind('"', 0, e.pos + 1)

                        if offending_quote_pos != -1:
                            # Check if it's already escaped. If so, this heuristic can't help.
                            if offending_quote_pos > 0 and json_str[offending_quote_pos - 1] == '\\':
                                logging.error(f"JSON repair failed on attempt {attempt + 1}. Found an escaped quote near the error, indicating a different issue. Error: {e}")
                                command_json = None
                                break

                            # Insert an escape character.
                            logging.warning(f"Attempting JSON repair on attempt {attempt + 1}. Found potential unescaped quote at position {offending_quote_pos}. Error: {e}")
                            json_str = json_str[:offending_quote_pos] + '\\' + json_str[offending_quote_pos:]
                        else:
                            # If no quote is found near the error, we can't fix it.
                            logging.error(f"JSON repair failed on attempt {attempt + 1}. Could not identify a quote to escape. Error: {e}")
                            command_json = None
                            break # Exit loop
                # --- End of repair loop ---

                if command_json and attachment_text:
                    command_json['attachment'] = attachment_text
                    audit_log.log_event("Socket.IO Emit: log_message", session_id=session_id, session_name=get_current_session_name(), loop_id=loop_id, source="Orchestrator", destination="Client", observers=["User"], details={'type': 'info', 'data': attachment_text})
                    socketio.emit('log_message', {'type': 'info', 'data': attachment_text}, to=session_id)

            if not command_json:
                logging.warning(f"Could not decode JSON from model response, even after repair attempts. Treating as plain text. Response: {response_text}")
                command_json = {"action": "respond", "parameters": {"response": response_text}}
            """
            
            # --- NEW, ROBUST JSON PARSING LOGIC ---
            command_json = None
            json_str, attachment_text = find_and_extract_json_with_prose(response_text)

            debugpy.breakpoint()

            if json_str:
                # A potential JSON block was found. Try to parse/heal it.
                max_repair_attempts = 10
                for attempt in range(max_repair_attempts):
                    try:
                        command_json = json.loads(json_str)
                        if attempt > 0:
                            logging.info(f"Successfully repaired JSON after {attempt} attempts.")
                        break # Success!
                    except json.JSONDecodeError as e:
                        offending_quote_pos = json_str.rfind('"', 0, e.pos + 1)
                        if offending_quote_pos != -1:
                            logging.warning(f"Attempting JSON repair {attempt + 1}/{max_repair_attempts}. Error: {e}")
                            json_str = json_str[:offending_quote_pos] + '\\' + json_str[offending_quote_pos:]
                        else:
                            logging.error(f"JSON repair failed on attempt {attempt+1}. Could not find quote to escape.")
                            command_json = None
                            break # Unfixable error

                if command_json and attachment_text:
                    command_json['attachment'] = attachment_text
                    audit_log.log_event("Socket.IO Emit: log_message", session_id=session_id, session_name=get_current_session_name(), loop_id=loop_id, source="Orchestrator", destination="Client", observers=["User"], details={'type': 'info', 'data': attachment_text})
                    socketio.emit('log_message', {'type': 'info', 'data': attachment_text}, to=session_id)

            if not command_json:
                # If no JSON was found or parsing/healing failed, treat the whole response as prose.
                logging.warning(f"Could not decode JSON from model response. Treating as plain text.")
                command_json = {"action": "respond", "parameters": {"response": response_text}}
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
