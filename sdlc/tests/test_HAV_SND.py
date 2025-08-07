import pytest
from unittest.mock import MagicMock, patch
from haven import Haven, Content, Part

# Test Protocol for the Haven.send_message method

@pytest.fixture
def mock_haven_with_session(mocker):
    """Fixture to create a Haven instance with a mocked model and a live session."""
    # Mock the global model object
    mock_model = MagicMock()
    # Configure the mock response from the model
    mock_response_content = Content(role="model", parts=[Part.from_text("Model response")])
    mock_model.generate_content.return_value.candidates = [MagicMock(content=mock_response_content)]
    
    mocker.patch('haven.model', mock_model)

    # Patch the global session dictionary and create the instance
    with patch('haven.live_chat_sessions', {}) as mock_sessions:
        instance = Haven()
        session_name = "test_session"
        instance.get_or_create_session(session_name, history_dicts=[])
        yield instance, mock_sessions, session_name, mock_model

def test_HAV_SND_001_to_004_send_message_flow(mock_haven_with_session):
    """
    Tests HAV-SND-001: Appends user prompt to history.
    Tests HAV-SND-002: Calls the generative model.
    Tests HAV-SND-003: Appends model response to history.
    Tests HAV-SND-004: Returns the correct dictionary.
    """
    instance, sessions, session_name, mock_model = mock_haven_with_session
    user_prompt = "Hello, model!"
    
    # --- Execution ---
    result = instance.send_message(session_name, user_prompt)

    # --- Verification ---
    history = sessions[session_name]
    
    # Requirement HAV-SND-001
    assert history[-2].role == "user"
    assert history[-2].parts[0].text == user_prompt
    
    # Requirement HAV-SND-002
    mock_model.generate_content.assert_called_once()
    
    # Requirement HAV-SND-003
    assert history[-1].role == "model"
    assert history[-1].parts[0].text == "Model response"

    # Requirement HAV-SND-004
    assert result == {"status": "success", "text": "Model response"}
