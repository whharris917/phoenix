import pytest
from response_parser import parse_agent_response
from data_models import ToolCommand

# Test Protocol for the parse_agent_response function

def test_RSP_PAR_001_and_002_fenced_command():
    """
    Tests RSP-PAR-001: Correctly parses prose and command.
    Tests RSP-PAR-002: Successfully extracts a command from ```json fences.
    """
    input_string = 'Here is the file. ```json\n{"action": "create_file", "parameters": {"filename": "a.txt"}}\n```'
    result = parse_agent_response(input_string)
    
    assert result.prose == "Here is the file."
    assert result.command is not None
    assert result.command.action == "create_file"
    assert result.command.parameters == {"filename": "a.txt"}

def test_RSP_PAR_003_unfenced_command():
    """
    Tests RSP-PAR-003: Falls back to brace-counting for unfenced JSON.
    """
    input_string = 'Okay, I will do that. {"action": "list_directory", "parameters": {}}'
    result = parse_agent_response(input_string)

    assert result.prose == "Okay, I will do that."
    assert result.command is not None
    assert result.command.action == "list_directory"

def test_RSP_PAR_004_malformed_command_repair():
    """
    Tests RSP-PAR-004: Attempts to repair malformed JSON.
    """
    # This JSON has an unescaped newline that should be repaired.
    input_string = '```json\n{"action": "create_file", "parameters": {"content": "line1\nline2"}}\n```'
    result = parse_agent_response(input_string)

    assert result.command is not None
    assert result.command.parameters["content"] == "line1\\nline2"

def test_RSP_PAR_005_no_command_found():
    """
    Tests RSP-PAR-005: Treats the entire string as prose if no command is found.
    """
    input_string = "This is just a simple sentence without any command."
    result = parse_agent_response(input_string)

    assert result.prose == input_string
    assert result.command is None
