# All but "Failure Mode 3 (Inconsistent Quotes)" worked

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

    if False:
        # First, do a pass for single quotes, which is a common and safe fix.
        # Handles keys: 'key' -> "key"
        s = re.sub(r"'([^']*)'\s*:", r'"\1":', s)
        # Handles values: : 'value' -> : "value"
        s = re.sub(r":\s*'([^']*)'", r': "\1"', s)

    s_before_loop = s
    max_iterations = 1000  # Safety break to prevent infinite loops

    for _ in range(max_iterations):
        try:
            json.loads(s)
            # If parsing succeeds, the JSON is valid.
            return s
        except json.JSONDecodeError as e:
            error_fixed = False
            
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