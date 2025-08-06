import pytest
import json
from pathlib import Path
from response_parser import parse_agent_response
from data_models import ToolCommand

# --- Test Data Loading ---


def load_test_cases():
    """Loads test cases from the JSON file."""
    # Construct a path to the JSON file relative to this test file
    json_path = Path(__file__).parent / "test_data" / "response_parser_cases.json"
    with open(json_path, "r") as f:
        test_cases = json.load(f)

    # Format the data for pytest.mark.parametrize
    # It expects a list of tuples: [(name, input, expected), (name, input, expected), ...]
    return [(case, test_cases[case]["response_text"], test_cases[case]["expected_output"]) for case in test_cases]


# --- The Parametrized Test ---


@pytest.mark.parametrize("name, test_input, expected", load_test_cases())
def test_parse_agent_response(name, test_input, expected):
    """
    Tests the parse_agent_response function with a variety of cases from a JSON file.
    'name', 'test_input', and 'expected' are automatically fed by pytest from our JSON file.
    """
    # 1. ACT: Call the function we are testing
    prose, command, prose_is_empty = parse_agent_response(test_input)

    # 2. ASSERT: Check the results against the expected output from the JSON file
    assert prose == expected["prose"]
    # assert prose_is_empty == expected["prose_is_empty"]

    if expected["command"] is None:
        assert command is None
    else:
        assert isinstance(command, ToolCommand)
        assert command.action == expected["command"]["action"]
        assert command.parameters == expected["command"]["parameters"]
