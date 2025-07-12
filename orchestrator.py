import json
import logging
from eventlet import tpool
from eventlet.event import Event
from tool_agent import execute_tool_command

confirmation_events = {}

def execute_reasoning_loop(socketio, session_data, initial_prompt, session_id, chat_sessions, model, api_stats):
    try:
        current_prompt = initial_prompt
        destruction_confirmed = False

        if isinstance(session_data, dict):
            chat = session_data.get('chat')
        else:
            chat = session_data

        if not chat:
            logging.error(f"Could not find chat object for session {session_id}")
            socketio.emit('log_message', {'type': 'error', 'data': 'Critical error: Chat session object not found.'}, to=session_id)
            return

        for i in range(15):
            socketio.sleep(0)
            
            response = tpool.execute(chat.send_message, current_prompt)
            
            if response.usage_metadata:
                api_stats['total_calls'] += 1
                api_stats['total_prompt_tokens'] += response.usage_metadata.prompt_token_count
                api_stats['total_completion_tokens'] += response.usage_metadata.candidates_token_count
                socketio.emit('api_usage_update', api_stats)
            
            response_text = response.text

            try:
                command_json = json.loads(response_text[response_text.find('{'):response_text.rfind('}')+1])
            except json.JSONDecodeError as e:
                error_message = f"Protocol Violation: My response was not valid JSON. Error: {e}. Full response: {response_text}"
                logging.error(error_message)
                socketio.emit('log_message', {'type': 'error', 'data': error_message})
                current_prompt = f"TOOL_RESULT: {json.dumps({'status': 'error', 'message': error_message})}"
                continue
            
            action = command_json.get("action")

            if action == 'respond':
                response_to_user = command_json.get('parameters', {}).get('response', '')
                socketio.emit('log_message', {'type': 'final_answer', 'data': response_to_user})
                current_prompt = f"TOOL_RESULT: {json.dumps({'status': 'success', 'message': 'Your response was delivered to the user.'})}"
                continue
            
            # --- MODIFIED: Enhanced task_complete action ---
            if action == 'task_complete':
                final_response = command_json.get('parameters', {}).get('response')
                if final_response:
                    socketio.emit('log_message', {'type': 'final_answer', 'data': final_response})
                logging.info(f"Agent initiated task_complete. Ending loop for session {session_id}.")
                return

            destructive_actions = ['delete_file', 'delete_session']
            if action in destructive_actions and not destruction_confirmed:
                err_msg = f"Action '{action}' is destructive and requires user confirmation. I must use 'request_confirmation' first."
                logging.warning(err_msg)
                current_prompt = f"TOOL_RESULT: {json.dumps({'status': 'error', 'message': err_msg})}"
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
                    destruction_confirmed = True
                else:
                    destruction_confirmed = False
                current_prompt = f"USER_CONFIRMATION: '{user_response}'"
                continue

            # --- MODIFIED: Silent Operator tool execution ---
            tool_result = execute_tool_command(command_json, session_id, chat_sessions, model)
            destruction_confirmed = False

            # --- NEW: Emit tool_log on success ---
            if tool_result.get('status') == 'success':
                log_message = tool_result.get('message', f"Tool '{action}' executed successfully.")
                socketio.emit('tool_log', {'data': f"[{log_message}]"}, to=session_id)
            
            if action in ['save_session', 'load_session', 'delete_session']:
                sessions_result = execute_tool_command({'action': 'list_sessions'}, session_id, chat_sessions, model)
                socketio.emit('session_list_update', sessions_result, to=session_id)

                if (action == 'save_session' or action == 'load_session') and tool_result.get('status') == 'success':
                    new_name = command_json.get('parameters', {}).get('session_name')
                    session_data = chat_sessions[session_id]
                    if isinstance(session_data, dict):
                        session_data['name'] = new_name
                    socketio.emit('session_name_update', {'name': new_name}, to=session_id)

                if action == 'delete_session' and tool_result.get('status') == 'success':
                    deleted_name = command_json.get('parameters', {}).get('session_name')
                    current_name = session_data.get('name') if isinstance(session_data, dict) else None
                    if deleted_name == current_name:
                        if isinstance(session_data, dict):
                            session_data['name'] = None
                        socketio.emit('session_name_update', {'name': None}, to=session_id)

                if action == 'load_session' and tool_result.get('status') == 'success':
                    history = tool_result.get('history')
                    if history:
                        socketio.emit('load_chat_history', {'history': history}, to=session_id)
                    return 

            current_prompt = f"TOOL_RESULT: {json.dumps(tool_result)}"

    except Exception as e:
        logging.exception("An error occurred in the reasoning loop.")
        socketio.emit('log_message', {'type': 'error', 'data': f"An error occurred during reasoning: {str(e)}"})
