import pytest
from response_parser import _repair_json

# Test Protocol for the _repair_json function

@pytest.mark.parametrize("test_id, malformed_json, expected_repaired_json", [
    (
        "RSP_RPJ_001_TC1",
        '{"notes": "This is a string with a newline\ncharacter"}',
        '{"notes": "This is a string with a newline\\ncharacter"}'
    ),
    (
        "RSP_RPJ_001_TC2",
        '{"quote": "This is an "unescaped" quote"}',
        '{"quote": "This is an \\"unescaped\\" quote"}'
    )
])
def test_RSP_RPJ_001_json_repair(test_id, malformed_json, expected_repaired_json):
    """
    Tests RSP-RPJ-001: Fixes common JSON errors.
    """
    repaired_json = _repair_json(malformed_json)
    assert repaired_json == expected_repaired_json
