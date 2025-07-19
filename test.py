
import json
import IPython

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

response_text = '```json { "action": "create_file", "parameters": { "a": "b" } } ```'

start_index, end_index = find_json_block(response_text)

if start_index is not None:
    json_str = response_text[start_index:end_index]
    IPython.embed()
    attachment_text = response_text[:start_index].strip().strip('```json')
    command_json = json.loads(json_str)

    if attachment_text:
        command_json['attachment'] = attachment_text
        print("AUDIT LOG AND SOCKET EMIT")
else:
	attachment_text = None
	command_json = {"action": "respond", "parameters": {"response": response_text}}

print(attachment_text)
print(command_json)