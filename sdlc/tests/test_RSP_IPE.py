import pytest
from response_parser import is_prose_effectively_empty

# Test Protocol for the is_prose_effectively_empty function

@pytest.mark.parametrize("test_id, input_string, expected_result", [
    ("RSP_IPE_001_TC1", None, True),
    ("RSP_IPE_001_TC2", "", True),
    ("RSP_IPE_001_TC3", "  ", True),
    ("RSP_IPE_001_TC4", "[06AUG2025_040527PM]", True),
    ("RSP_IPE_001_TC5", " [06AUG2025_040527PM] ", True),
    ("RSP_IPE_002_TC1", "Hello world", False),
    ("RSP_IPE_002_TC2", "[06AUG2025_040527PM] Hello", False),
])
def test_RSP_IPE_001_and_002_prose_emptiness(test_id, input_string, expected_result):
    """
    Tests RSP-IPE-001: Returns True for effectively empty strings.
    Tests RSP-IPE-002: Returns False for strings with meaningful content.
    """
    assert is_prose_effectively_empty(input_string) == expected_result
