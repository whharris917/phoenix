import pytest
from response_parser import _handle_payloads
from data_models import ToolCommand

# Test Protocol for the _handle_payloads function

def test_RSP_HPL_001_and_002_and_003_payload_handling():
    """
    Tests RSP-HPL-001: Identifies payload placeholders.
    Tests RSP-HPL-002: Replaces placeholders with content.
    Tests RSP-HPL-003: Removes payload blocks from prose.
    """
    prose = "Here is the script: START @@script_content print('hello') END @@script_content. I will execute it now."
    command = ToolCommand(action="execute_python_script", parameters={"script_content": "@@script_content"})
    
    # --- Execution ---
    new_prose, new_command = _handle_payloads(prose, command)

    # --- Verification ---
    # Requirement RSP-HPL-002
    assert new_command.parameters["script_content"] == "print('hello')"
    
    # Requirement RSP-HPL-003
    assert "START @@script_content" not in new_prose
    assert "END @@script_content" not in new_prose
    assert new_prose == "Here is the script: . I will execute it now."
