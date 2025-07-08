import json
import logging
from eventlet.event import Event
from tool_agent import execute_tool_command

confirmation_events = {}

def execute_reasoning_loop(socketio, chat, initial_prompt, session_id, chat_sessions, model):
    try:
        current_prompt = initial_prompt
        for i in range(10):
            socketio.sleep(0)
            response = chat.send_message(current_prompt)
            response_text = response.text
            if "{" in response_text and "}" in response_text:
                command_json = json.loads(response_text.strip().replace('```json', '').replace('```', ''))
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
                
                tool_result = execute_tool_command(command_json, session_id, chat_sessions, model)
                
                socketio.emit('agent_action', {'type': 'Result', 'data': tool_result})
                current_prompt = f"TOOL_RESULT: {json.dumps(tool_result)}"
            else:
                socketio.emit('log_message', {'type': 'final_answer', 'data': response_text})
                return
    except Exception as e:
        logging.exception("An error occurred in the reasoning loop.")
        socketio.emit('log_message', {'type': 'error', 'data': f"An error occurred during reasoning: {str(e)}"})