import json
import logging
import re
from eventlet import tpool
from eventlet.event import Event
from tool_agent import execute_tool_command

confirmation_events = {}

def execute_reasoning_loop(socketio, session_data, initial_prompt, session_id, chat_sessions, model, api_stats):
    try:
        current_prompt = initial_prompt
        # --- NEW: Safety lock for destructive operations ---
        destruction_confirmed = False

        if isinstance(session_data, dict):
            chat = session_data.get('chat')
        else:
            chat = session_data

        if not chat:
            logging.error(f"Could not find chat object for session {session_id}")
            socketio.emit('log_message', {'type': 'error', 'data': 'Critical error: Chat session object not found.'}, to=session_id)
            return

        for i in range(10):
            socketio.sleep(0)
            
            response = tpool.execute(chat.send_message, current_prompt)
            
            if response.usage_metadata:
                api_stats['total_calls'] += 1
                api_stats['total_prompt_tokens'] += response.usage_metadata.prompt_token_count
                api_stats['total_completion_tokens'] += response.usage_metadata.candidates_token_count
                socketio.emit('api_usage_update', api_stats)
            
            response_text = response.text

            command_json = None
            json_match = re.search(r'```json\n(.*?)\n```', response_text, re.DOTALL)
            if json_match:
                json_str = json_match.group(1).strip()
                try:
                    command_json = json.loads(json_str)
                except json.JSONDecodeError as e:
                    logging.error(f"JSON parsing failed for: {json_str}. Error: {e}")
                    command_json = None
            
            if command_json:
                action = command_json.get("action")
                
                # --- SAFETY LOCK LOGIC ---
                destructive_actions = ['delete_file', 'delete_session']
                if action in destructive_actions and not destruction_confirmed:
                    # If a destructive action is attempted without confirmation, deny it.
                    err_msg = f"Action '{action}' is destructive and requires user confirmation. I must use 'request_confirmation' first."
                    logging.warning(err_msg)
                    current_prompt = f"TOOL_RESULT: {json.dumps({'status': 'error', 'message': err_msg})}"
                    # Reset the flag after a failed attempt
                    destruction_confirmed = False
                    continue

                if action == 'request_confirmation':
                    prompt_text = command_json.get('parameters', {}).get('prompt', 'Are you sure?')
                    confirmation_event = Event()
                    confirmation_events[session_id] = confirmation_event
                    socketio.emit('request_user_confirmation', {'prompt': prompt_text}, to=session_id)
                    user_response = confirmation_event.wait()
                    confirmation_events.pop(session_id, None)
                    if user_response == 'yes':
                        destruction_confirmed = True # Unlock for the next step
                    else:
                        destruction_confirmed = False # Ensure lock remains
                    current_prompt = f"USER_CONFIRMATION: '{user_response}'"
                    continue

                socketio.emit('log_message', {'type': 'thought', 'data': f"I should use the '{action}' tool."})
                socketio.emit('agent_action', {'type': 'Executing', 'data': command_json})
                
                tool_result = execute_tool_command(command_json, session_id, chat_sessions, model)

                # Reset the lock after any tool execution
                destruction_confirmed = False
                
                socketio.emit('agent_action', {'type': 'Result', 'data': tool_result})
                
                if action in ['save_session', 'load_session', 'delete_session']:
                    sessions_result = execute_tool_command({'action': 'list_sessions'}, session_id, chat_sessions, model)
                    socketio.emit('session_list_update', sessions_result, to=session_id)

                    if (action == 'save_session' or action == 'load_session') and tool_result.get('status') == 'success':
                        new_name = command_json.get('parameters', {}).get('session_name')
                        session_data = chat_sessions[session_id]
                        if isinstance(session_data, dict):
                            session_data['name'] = new_name
                        socketio.emit('session_name_update', {'name': new_name}, to=session_id)

                    if action == 'load_session' and tool_result.get('status') == 'success':
                        history = tool_result.get('history')
                        if history:
                            socketio.emit('load_chat_history', {'history': history}, to=session_id)
                        return 

                current_prompt = f"TOOL_RESULT: {json.dumps(tool_result)}"
            else:
                socketio.emit('log_message', {'type': 'final_answer', 'data': response_text})
                return
    except Exception as e:
        logging.exception("An error occurred in the reasoning loop.")
        socketio.emit('log_message', {'type': 'error', 'data': f"An error occurred during reasoning: {str(e)}"})