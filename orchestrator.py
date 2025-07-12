# --- orchestrator.py ---

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

        if not isinstance(session_data, dict):
             logging.error(f"Session data for {session_id} is not a dictionary.")
             return

        chat = session_data.get('chat')
        memory = session_data.get('memory') # Get the memory manager instance

        if not chat or not memory:
            logging.error(f"Could not find chat or memory object for session {session_id}")
            socketio.emit('log_message', {'type': 'error', 'data': 'Critical error: Chat or Memory session object not found.'}, to=session_id)
            return

        observation_template = """
        OBSERVATION:
        This is an automated observation from a tool you just invoked. It is NOT a message from the human user.
        Analyze the following tool result and decide on the next step in your plan.
        DO NOT interpret this as agreement, confirmation, or approval from the user to proceed with any plan you may have for your next action.
        Tool Result:
        {tool_result_json}
        """

        for i in range(15):
            socketio.sleep(0)

            # --- NEW: RAG IMPLEMENTATION ---
            # 1. Get relevant context from long-term memory (Tier 3)
            retrieved_context = memory.get_context_for_prompt(current_prompt)
            
            # 2. Construct the final prompt with the retrieved context
            final_prompt = current_prompt
            if retrieved_context:
                context_str = "\n".join(retrieved_context)
                # Prepend the retrieved context to the user's prompt
                final_prompt = (
                    "CONTEXT FROM PAST CONVERSATIONS:\n"
                    f"{context_str}\n\n"
                    "Based on the above context, please respond to the following prompt:\n"
                    f"{current_prompt}"
                )
                logging.info(f"Augmented prompt with {len(retrieved_context)} documents from memory.")

            # --- END NEW ---

            # Add user's prompt to memory before sending to model
            memory.add_turn("user", current_prompt)

            # Use the final_prompt (which may be augmented)
            response = tpool.execute(chat.send_message, final_prompt)

            if response.usage_metadata:
                api_stats['total_calls'] += 1
                api_stats['total_prompt_tokens'] += response.usage_metadata.prompt_token_count
                api_stats['total_completion_tokens'] += response.usage_metadata.candidates_token_count
                socketio.emit('api_usage_update', api_stats)
            
            response_text = response.text
            
            # Add model's response to memory
            memory.add_turn("model", response_text)

            try:
                # Using a more robust method to find the JSON object
                start_index = response_text.find('{')
                end_index = response_text.rfind('}') + 1
                if start_index == -1 or end_index == 0:
                    raise json.JSONDecodeError("No JSON object found", response_text, 0)
                
                json_str = response_text[start_index:end_index]
                command_json = json.loads(json_str)

            except json.JSONDecodeError as e:
                error_message = f"Protocol Violation: My response was not valid JSON. Error: {e}. Full response: {response_text}"
                logging.error(error_message)
                # We will now use the structured observation format for errors as well
                error_payload = {'status': 'error', 'message': error_message}
                current_prompt = observation_template.format(tool_result_json=json.dumps(error_payload))
                continue
            
            action = command_json.get("action")

            if action == 'respond':
                response_to_user = command_json.get('parameters', {}).get('response', '')
                socketio.emit('log_message', {'type': 'final_answer', 'data': response_to_user})
                # Use the new observation template
                # Use a more factual and less ambiguous response
                result_payload = {'status': 'success', 'action_taken': 'respond', 'details': 'The message was successfully sent to the user.'}
                current_prompt = observation_template.format(tool_result_json=json.dumps(result_payload))
                continue
            
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
                
                error_payload = {'status': 'error', 'message': err_msg}
                current_prompt = observation_template.format(tool_result_json=json.dumps(error_payload))
                destruction_confirmed = False # Ensure it's reset
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

            tool_result = execute_tool_command(command_json, session_id, chat_sessions, model)
            destruction_confirmed = False # Reset lock after any successful tool use

            if tool_result.get('status') == 'success':
                log_message = tool_result.get('message', f"Tool '{action}' executed successfully.")
                socketio.emit('tool_log', {'data': f"[{log_message}]"}, to=session_id)
            
            if action in ['save_session', 'load_session', 'delete_session']:
                sessions_result = execute_tool_command({'action': 'list_sessions'}, session_id, chat_sessions, model)
                socketio.emit('session_list_update', sessions_result, to=session_id)

                if (action == 'save_session' or action == 'load_session') and tool_result.get('status') == 'success':
                    new_name = command_json.get('parameters', {}).get('session_name')
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
                        # Also update the memory manager's buffer when loading a session
                        memory.conversational_buffer = history
                        socketio.emit('load_chat_history', {'history': history}, to=session_id)
                    return 

            current_prompt = observation_template.format(tool_result_json=json.dumps(tool_result))

    except Exception as e:
        logging.exception("An error occurred in the reasoning loop.")
        socketio.emit('log_message', {'type': 'error', 'data': f"An error occurred during reasoning: {str(e)}"})