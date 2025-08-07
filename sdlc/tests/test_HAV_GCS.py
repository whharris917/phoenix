import pytest
from unittest.mock import patch
from haven import Haven

# Test Protocol for the Haven.get_or_create_session method

@pytest.fixture
def haven_instance():
    """A pytest fixture to create a clean Haven instance for each test."""
    # We patch 'live_chat_sessions' to isolate the test
    with patch('haven.live_chat_sessions', {}) as mock_sessions:
        instance = Haven()
        # Yield both the instance and the mock dictionary for inspection
        yield instance, mock_sessions

def test_HAV_GCS_001_create_new_session(haven_instance):
    """
    Tests HAV-GCS-001: Creates a new session if one does not exist.
    """
    instance, sessions = haven_instance
    session_name = "new_session"
    
    assert session_name not in sessions
    instance.get_or_create_session(session_name, history_dicts=[])
    assert session_name in sessions

def test_HAV_GCS_002_use_existing_session(haven_instance):
    """
    Tests HAV-GCS-002: Uses an existing session if the name matches.
    """
    instance, sessions = haven_instance
    session_name = "existing_session"
    sessions[session_name] = ["some_history"] # Pre-populate the session
    
    instance.get_or_create_session(session_name, history_dicts=[])
    # Verify that the history was not overwritten
    assert sessions[session_name] == ["some_history"]
