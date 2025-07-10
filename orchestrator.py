import json
import logging
from eventlet.event import Event
from tool_agent import execute_tool_command

confirmation_events = {}

# MODIFIED: Function signature updated to accept api_stats
def execute_reasoning_loop(socketio, session_data, initial_prompt, session_id, chat_sessions, model, api_stats):
    try:
        current_prompt = initial_prompt
        
        # MODIFIED: Safely unpack the chat object from the session_data.
        # This prevents the "not subscriptable" error if the data structure is incorrect.
        if isinstance(session_data, dict):
            chat = session_data.get('chat')
        else:
            # Fallback for the case where session_data is the raw ChatSession object
            chat = session_data

        if not chat:
            logging.error(f"Could not find chat object for session {session_id}")
            socketio.emit('log_message', {'type': 'error', 'data': 'Critical error: Chat session object not found.'}, to=session_id)
            return

        for i in range(10):
            socketio.sleep(0)
            
            # --- API Call and Usage Tracking ---
            response = chat.send_message(current_prompt)
            
            # NEW: Track API usage metadata
            if response.usage_metadata:
                api_stats['total_calls'] += 1
                api_stats['total_prompt_tokens'] += response.usage_metadata.prompt_token_count
                api_stats['total_completion_tokens'] += response.usage_metadata.candidates_token_count
                # Emit the updated stats to the client
                socketio.emit('api_usage_update', api_stats)
            
            response_text = response.text
            
            if "{" in response_text and "}" in response_text:
                try:
                    start_index = response_text.find('{')
                    end_index = response_text.rfind('}') + 1
                    json_str = response_text[start_index:end_index]
                    command_json = json.loads(json_str)
                except (json.JSONDecodeError, IndexError):
                    socketio.emit('log_message', {'type': 'final_answer', 'data': response_text})
                    return

                action = command_json.get("action")
                
                if action == 'request_confirmation':
                    prompt_text = command_json.get('parameters', {}).get('prompt', 'Are you sure?')
                    confirmation_event = Event()
                    confirmation_events[session_id] = confirmation_event
                    socketio.emit('request_user_confirmation', {'prompt': prompt_text}, to=session_id)
                    user_response = confirmation_event.wait()
                    confirmation_events.pop(session_id, None)
                    current_prompt = f"USER_CONFIRMATION: '{user_response}'"
                    continue

                socketio.emit('log_message', {'type': 'thought', 'data': f"I should use the '{action}' tool."})
                socketio.emit('agent_action', {'type': 'Executing', 'data': command_json})
                
                # Pass the session_data object to the tool command
                tool_result = execute_tool_command(command_json, session_id, chat_sessions, model)
                
                socketio.emit('agent_action', {'type': 'Result', 'data': tool_result})
                
                # After a tool is used, let the orchestrator know if the session list or name needs an update
                if action in ['save_session', 'load_session', 'delete_session']:
                    sessions_result = execute_tool_command({'action': 'list_sessions'}, session_id, chat_sessions, model)
                    socketio.emit('session_list_update', sessions_result, to=session_id)
                    # If a session was saved or loaded, update the name for this client
                    if (action == 'save_session' or action == 'load_session') and tool_result.get('status') == 'success':
                        new_name = command_json.get('parameters', {}).get('session_name')
                        if isinstance(session_data, dict):
                            session_data['name'] = new_name
                        socketio.emit('session_name_update', {'name': new_name}, to=session_id)

                current_prompt = f"TOOL_RESULT: {json.dumps(tool_result)}"
            else:
                socketio.emit('log_message', {'type': 'final_answer', 'data': response_text})
                return
    except Exception as e:
        logging.exception("An error occurred in the reasoning loop.")
        socketio.emit('log_message', {'type': 'error', 'data': f"An error occurred during reasoning: {str(e)}"})
