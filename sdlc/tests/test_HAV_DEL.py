import pytest
from unittest.mock import patch
from haven import Haven

# Test Protocol for the Haven.delete_session method

@pytest.fixture
def haven_with_live_session():
    """Fixture to create a Haven instance with a pre-existing session."""
    with patch('haven.live_chat_sessions', {"session_to_delete": []}) as mock_sessions:
        instance = Haven()
        yield instance, mock_sessions

def test_HAV_DEL_001_delete_session(haven_with_live_session):
    """
    Tests HAV-DEL-001: Removes the specified session from the in-memory dictionary.
    """
    instance, sessions = haven_with_live_session
    session_name = "session_to_delete"

    assert session_name in sessions
    instance.delete_session(session_name)
    assert session_name not in sessions
