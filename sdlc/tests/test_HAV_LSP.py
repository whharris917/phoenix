import pytest
from unittest.mock import mock_open, patch
from haven import load_system_prompt

# Test Protocol for the load_system_prompt function

def test_HAV_LSP_001_load_success(mocker):
    """
    Tests HAV-LSP-001: Successfully loads the prompt file.
    We use a mock to simulate the file existing.
    """
    mock_content = "This is the system prompt."
    # Simulate the 'open' built-in function
    mocker.patch('builtins.open', mock_open(read_data=mock_content))
    # Simulate 'os.path.join' to avoid dependency on file structure
    mocker.patch('os.path.join', return_value='fake/path/system_prompt.txt')
    
    prompt = load_system_prompt()
    assert prompt == mock_content

def test_HAV_LSP_002_load_failure(mocker):
    """
    Tests HAV-LSP-002: Returns a default message when the file is not found.
    """
    # Simulate 'open' raising a FileNotFoundError
    mocker.patch('builtins.open', side_effect=FileNotFoundError)
    mocker.patch('os.path.join', return_value='fake/path/system_prompt.txt')

    prompt = load_system_prompt()
    assert "unable to locate or open system_prompt.txt" in prompt
