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
    """
    Finds the JSON block in a string by working backwards from the end
    and balancing curly braces.
    """
    end_index = text.rfind('}')
    if end_index == -1:
        return None, None # No JSON object found

    brace_count = 1
    start_index = -1

    for i in range(end_index - 1, -1, -1):
        char = text[i]
        if char == '}':
            brace_count += 1
        elif char == '{':
            brace_count -= 1
        
        if brace_count == 0:
            start_index = i
            break

    if start_index == -1:
        return None, None # Malformed or incomplete JSON

    return start_index, end_index + 1

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

            try:
                start_index, end_index = find_json_block(response_text)
                
                if start_index is not None:
                    json_str = response_text[start_index:end_index]
                    attachment_text = response_text[:start_index].strip().strip('```json')
                    command_json = json.loads(json_str)

                    if attachment_text:
                        command_json['attachment'] = attachment_text
                        audit_log.log_event("Socket.IO Emit: log_message", session_id=session_id, session_name=get_current_session_name(), loop_id=loop_id, source="Orchestrator", destination="Client", observers=["User"], details={'type': 'info', 'data': attachment_text})
                        socketio.emit('log_message', {'type': 'info', 'data': attachment_text}, to=session_id)
                else:
                    debugpy.breakpoint()
                    command_json = {"action": "respond", "parameters": {"response": response_text}}

            except json.JSONDecodeError:
                debugpy.breakpoint()
                logging.warning(f"Could not decode JSON from model response. Treating as plain text. Response: {response_text}")
                command_json = {"action": "respond", "parameters": {"response": response_text}}

            action = command_json.get("action")

            if action == 'respond':
                response_to_user = command_json.get('parameters', {}).get('response', '')
                audit_log.log_event("Socket.IO Emit: log_message", session_id=session_id, session_name=get_current_session_name(), loop_id=loop_id, source="Orchestrator", destination="Client", observers=["User", "Orchestrator"], details={'type': 'final_answer', 'data': response_to_user})
                socketio.emit('log_message', {'type': 'final_answer', 'data': response_to_user}, to=session_id)
                return
            
            if action == 'task_complete':
                final_response = command_json.get('parameters', {}).get('response')
                if final_response:
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
            else:
                pass

            current_prompt = observation_template.format(tool_result_json=json.dumps(tool_result))

    except Exception as e:
        logging.exception("An error occurred in the reasoning loop.")
        socketio.emit('log_message', {'type': 'error', 'data': f"An error occurred during reasoning: {str(e)}"}, to=session_id)
    finally:
        audit_log.log_event("Reasoning Loop Ended", session_id=session_id, session_name=get_current_session_name(), loop_id=loop_id, source="Orchestrator", destination="Orchestrator", observers=["Orchestrator"])
