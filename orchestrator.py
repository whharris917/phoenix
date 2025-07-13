import json
import logging
from eventlet import tpool
from eventlet.event import Event
from tool_agent import execute_tool_command
from audit_logger import audit_log

confirmation_events = {}

def execute_reasoning_loop(socketio, session_data, initial_prompt, session_id, chat_sessions, model, api_stats):
    session_name = chat_sessions.get(session_id, {}).get('name')
    audit_log.log_event("Reasoning Loop Started", session_id=session_id, session_name=session_name, source="Orchestrator", details={"initial_prompt": initial_prompt})
    
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
            audit_log.log_event("Socket.IO Emit: log_message", session_id=session_id, source="Orchestrator", details={'type': 'error', 'data': 'Critical error: Chat or Memory session object not found.'})
            socketio.emit('log_message', {'type': 'error', 'data': 'Critical error: Chat or Memory session object not found.'}, to=session_id)
            return

        observation_template = """
        OBSERVATION:
        This is an automated observation from a tool you just invoked. It is NOT a message from the human user.
        Analyze the following tool result and decide on the next step in your plan.
        DO NOT interpret this as confirmation from the user to proceed with any plan you may have for your next action.
        Tool Result:
        {tool_result_json}
        """

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

            audit_log.log_event("Gemini API Call Sent", session_id=session_id, session_name=session_name, source="Orchestrator", details={"prompt": final_prompt})
            response = tpool.execute(chat.send_message, final_prompt)
            audit_log.log_event("Gemini API Response Received", session_id=session_id, session_name=session_name, source="Orchestrator", details={"response_text": response.text})

            if response.usage_metadata:
                api_stats['total_calls'] += 1
                api_stats['total_prompt_tokens'] += response.usage_metadata.prompt_token_count
                api_stats['total_completion_tokens'] += response.usage_metadata.candidates_token_count
                audit_log.log_event("Socket.IO Emit: api_usage_update", session_id=session_id, session_name=session_name, source="Orchestrator", details=api_stats)
                socketio.emit('api_usage_update', api_stats)
            
            response_text = response.text
            memory.add_turn("model", response_text)

            if len(memory.conversational_buffer) >= memory.max_buffer_size:
                logging.info("Memory buffer full. Triggering summarization tool.")
                summarize_command = {"action": "summarize_and_condense_memory", "parameters": {}}
                
                audit_log.log_event("Tool Agent Call Sent", session_id=session_id, session_name=session_name, source="Orchestrator", details=summarize_command)
                tool_result = execute_tool_command(summarize_command, session_id, chat_sessions, model)
                audit_log.log_event("Tool Agent Execution Finished", session_id=session_id, session_name=session_name, source="Orchestrator", details=tool_result)

                logging.info(f"Summarization result: {tool_result.get('message')}")
                chat.history = memory.get_full_history()

            try:
                start_index = response_text.find('{')
                end_index = response_text.rfind('}') + 1
                if start_index == -1 or end_index == 0:
                    raise json.JSONDecodeError("No JSON object found", response_text, 0)
                json_str = response_text[start_index:end_index]
                command_json = json.loads(json_str)
            except json.JSONDecodeError as e:
                error_message = f"Protocol Violation: My response was not valid JSON. Error: {e}. Full response: {response_text}"
                logging.error(error_message)
                error_payload = {'status': 'error', 'message': error_message}
                current_prompt = observation_template.format(tool_result_json=json.dumps(error_payload))
                continue
            
            action = command_json.get("action")

            if action == 'respond':
                response_to_user = command_json.get('parameters', {}).get('response', '')
                audit_log.log_event("Socket.IO Emit: log_message", session_id=session_id, session_name=session_name, source="Orchestrator", details={'type': 'final_answer', 'data': response_to_user})
                socketio.emit('log_message', {'type': 'final_answer', 'data': response_to_user}, to=session_id)
                result_payload = {'status': 'success', 'action_taken': 'respond', 'details': 'The message was successfully sent to the user.'}
                current_prompt = observation_template.format(tool_result_json=json.dumps(result_payload))
                continue
            
            if action == 'task_complete':
                final_response = command_json.get('parameters', {}).get('response')
                if final_response:
                    audit_log.log_event("Socket.IO Emit: log_message", session_id=session_id, session_name=session_name, source="Orchestrator", details={'type': 'final_answer', 'data': final_response})
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
                audit_log.log_event("Socket.IO Emit: request_user_confirmation", session_id=session_id, session_name=session_name, source="Orchestrator", details={'prompt': prompt_text})
                socketio.emit('request_user_confirmation', {'prompt': prompt_text}, to=session_id)
                user_response = confirmation_event.wait()
                confirmation_events.pop(session_id, None)
                if user_response == 'yes':
                    destruction_confirmed = True
                else:
                    destruction_confirmed = False
                current_prompt = f"USER_CONFIRMATION: '{user_response}'"
                continue

            audit_log.log_event("Tool Agent Call Sent", session_id=session_id, session_name=session_name, source="Orchestrator", details=command_json)
            tool_result = execute_tool_command(command_json, session_id, chat_sessions, model)
            audit_log.log_event("Tool Agent Execution Finished", session_id=session_id, session_name=session_name, source="Orchestrator", details=tool_result)

            destruction_confirmed = False

            if tool_result.get('status') == 'success':
                log_message = tool_result.get('message', f"Tool '{action}' executed successfully.")
                audit_log.log_event("Socket.IO Emit: tool_log", session_id=session_id, session_name=session_name, source="Orchestrator", details={'data': f"[{log_message}]"})
                socketio.emit('tool_log', {'data': f"[{log_message}]"}, to=session_id)
            
            if action in ['save_session', 'load_session', 'delete_session']:
                sessions_result = execute_tool_command({'action': 'list_sessions'}, None, None, None)
                audit_log.log_event("Socket.IO Emit: session_list_update", session_id=session_id, session_name=session_name, source="Orchestrator", details=sessions_result)
                socketio.emit('session_list_update', sessions_result, to=session_id)

                if (action == 'save_session' or action == 'load_session') and tool_result.get('status') == 'success':
                    new_name = command_json.get('parameters', {}).get('session_name')
                    if isinstance(session_data, dict):
                        session_data['name'] = new_name
                    audit_log.log_event("Socket.IO Emit: session_name_update", session_id=session_id, session_name=new_name, source="Orchestrator", details={'name': new_name})
                    socketio.emit('session_name_update', {'name': new_name}, to=session_id)

                if action == 'delete_session' and tool_result.get('status') == 'success':
                    deleted_name = command_json.get('parameters', {}).get('session_name')
                    current_name = session_data.get('name') if isinstance(session_data, dict) else None
                    if deleted_name == current_name:
                        if isinstance(session_data, dict):
                            session_data['name'] = None
                        audit_log.log_event("Socket.IO Emit: session_name_update", session_id=session_id, source="Orchestrator", details={'name': None})
                        socketio.emit('session_name_update', {'name': None}, to=session_id)

                if action == 'load_session' and tool_result.get('status') == 'success':
                    history = tool_result.get('history')
                    if history:
                        memory.conversational_buffer = history
                        audit_log.log_event("Socket.IO Emit: load_chat_history", session_id=session_id, session_name=session_name, source="Orchestrator", details={'history_length': len(history)})
                        socketio.emit('load_chat_history', {'history': history}, to=session_id)
                    return 

            current_prompt = observation_template.format(tool_result_json=json.dumps(tool_result))

    except Exception as e:
        logging.exception("An error occurred in the reasoning loop.")
        audit_log.log_event("Socket.IO Emit: log_message", session_id=session_id, source="Orchestrator", details={'type': 'error', 'data': f"An error occurred during reasoning: {str(e)}"})
        socketio.emit('log_message', {'type': 'error', 'data': f"An error occurred during reasoning: {str(e)}"}, to=session_id)
    finally:
        audit_log.log_event("Reasoning Loop Ended", session_id=session_id, session_name=session_name, source="Orchestrator")