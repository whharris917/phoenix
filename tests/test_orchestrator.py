import pytest
from unittest.mock import MagicMock

# The function we are testing from your current file
from orchestrator import execute_reasoning_loop

# The data models we need
from data_models import ToolCommand, ToolResult


@pytest.fixture
def setup_mocks(mocker):
    """
    A pytest fixture to create mock objects for all external dependencies
    of the execute_reasoning_loop function.
    """
    # Mock the main dependencies
    mock_socketio = MagicMock()
    mock_chat = MagicMock()
    mock_memory = MagicMock()
    mock_haven_proxy = MagicMock()

    # REFACTORED: session_data is a dictionary, not an ActiveSession object yet.
    mock_session_data = {"chat": mock_chat, "memory": mock_memory, "name": "test-session"}

    # Use mocker.patch to replace the imported execute_tool_command function
    mock_execute_tool = mocker.patch("orchestrator.execute_tool_command")

    return {
        "socketio": mock_socketio,
        "session_data": mock_session_data,
        "chat": mock_chat,
        "memory": mock_memory,
        "execute_tool_command": mock_execute_tool,
        "initial_prompt": "List the files in the current directory.",
        "session_id": "test_socket_id",
        "chat_sessions": {"test_socket_id": mock_session_data},
        "haven_proxy": mock_haven_proxy,
    }


def test_reasoning_loop_list_files_scenario(setup_mocks):
    """
    Tests the current execute_reasoning_loop with a 2-turn scenario:
    1. Agent calls the 'list_directory' tool.
    2. Agent receives the tool result and provides a final answer.
    """
    # 1. ARRANGE: Configure the behavior of our mock dependencies
    mocks = setup_mocks  # Use a shorter variable name for clarity

    # Configure the mock LLM to return a tool command on the first call,
    # and a final answer on the second call.
    mocks["chat"].send_message.side_effect = [
        MagicMock(
            text="""
            ```json
            {
                "action": "list_directory",
                "parameters": {}
            }
            ```
        """
        ),
        MagicMock(
            text="""
            The files are: file1.txt, file2.py
            ```json
            {
                "action": "respond",
                "parameters": {
                    "response": "I found these files: file1.txt, file2.py"
                }
            }
            ```
        """
        ),
    ]

    mocks["memory"].get_context_for_prompt.return_value = []

    mocks["execute_tool_command"].return_value = ToolResult(status="success", message="Listed files in directory.", content=["file1.txt", "file2.py"])

    # 2. ACT: Call the global function directly with the mock objects
    execute_reasoning_loop(
        socketio=mocks["socketio"],
        session_data=mocks["session_data"],
        initial_prompt=mocks["initial_prompt"],
        session_id=mocks["session_id"],
        chat_sessions=mocks["chat_sessions"],
        haven_proxy=mocks["haven_proxy"],
    )

    # 3. ASSERT: Verify that the loop behaved correctly

    # Assert that the LLM was called twice
    assert mocks["chat"].send_message.call_count == 2

    # Assert that memory was updated for user prompt, model response, tool result (user), and final model response
    assert mocks["memory"].add_turn.call_count == 4

    # Assert that the tool command was executed exactly once
    mocks["execute_tool_command"].assert_called_once()

    # Check that the tool was called with the correct ToolCommand object
    tool_call_args = mocks["execute_tool_command"].call_args[0]
    called_command = tool_call_args[0]
    assert isinstance(called_command, ToolCommand)
    assert called_command.action == "list_directory"

    # Check that the final answer was emitted to the client
    final_answer_emitted = False
    for c in mocks["socketio"].emit.call_args_list:
        event_name, event_data = c[0]
        if event_name == "log_message" and event_data.get("type") == "final_answer":
            assert "I found these files: file1.txt, file2.py" in event_data["data"]
            final_answer_emitted = True

    assert final_answer_emitted, "The final answer was not emitted to the client."
