import unittest
import json
import sys
import os

# Add the parent directory to the path so we can import the orchestrator
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# It's better to import the specific function to be tested
from orchestrator import parse_agent_response

class TestParseAgentResponse(unittest.TestCase):
    """
    Unit tests for the parse_agent_response function in orchestrator.py.
    This suite covers various formats of agent responses to ensure the parser
    is robust and handles edge cases correctly.
    """

    def test_prose_only(self):
        """Tests a response containing only natural language."""
        response_text = "[2025-07-27 10:00:00] Hello, this is a simple prose message."
        prose, command, prose_is_empty = parse_agent_response(response_text)
        self.assertEqual(prose, response_text)
        self.assertIsNone(command)
        self.assertFalse(prose_is_empty)

    def test_command_only_with_fences(self):
        """Tests a response containing only a JSON command enclosed in fences."""
        response_text = """```json
{
    "action": "list_files",
    "parameters": {}
}
```"""
        prose, command, prose_is_empty = parse_agent_response(response_text)
        self.assertIsNone(prose)
        self.assertIsNotNone(command)
        self.assertEqual(command['action'], 'list_files')
        self.assertTrue(prose_is_empty)

    def test_command_only_no_fences(self):
        """Tests a response with a JSON command not enclosed in fences."""
        response_text = '{"action": "read_file", "parameters": {"filename": "test.txt"}}'
        prose, command, prose_is_empty = parse_agent_response(response_text)
        self.assertIsNone(prose)
        self.assertIsNotNone(command)
        self.assertEqual(command['action'], 'read_file')
        self.assertEqual(command['parameters']['filename'], 'test.txt')

    def test_mixed_message_prose_first(self):
        """Tests a mixed response with prose followed by a command."""
        response_text = """[2025-07-27 10:05:00] I will now list the files.
```json
{
    "action": "list_files",
    "parameters": {}
}
```"""
        prose, command, prose_is_empty = parse_agent_response(response_text)
        self.assertEqual(prose, "[2025-07-27 10:05:00] I will now list the files.")
        self.assertIsNotNone(command)
        self.assertEqual(command['action'], 'list_files')
        self.assertFalse(prose_is_empty)

    def test_malformed_json_needs_repair(self):
        """Tests that the parser can repair a JSON with an unescaped newline."""
        response_text = """[2025-07-27 10:10:00] Creating a file with a newline.
```json
{
    "action": "create_file",
    "parameters": {
        "filename": "test.txt",
        "content": "Line 1
Line 2"
    }
}
```"""
        prose, command, prose_is_empty = parse_agent_response(response_text)
        self.assertEqual(prose, "[2025-07-27 10:10:00] Creating a file with a newline.")
        self.assertIsNotNone(command)
        self.assertEqual(command['action'], 'create_file')
        # Check if the newline was correctly escaped
        self.assertEqual(command['parameters']['content'], "Line 1\nLine 2")

    def test_response_with_payload(self):
        """Tests that payload blocks are correctly ignored by the parser but kept in the prose."""
        response_text = """[2025-07-27 10:15:00] Here is the file content.
```json
{
    "action": "create_file",
    "parameters": {
        "filename": "script.py",
        "content": "@@PAYLOAD"
    }
}
```
START @@PAYLOAD
print("Hello, World!")
END @@PAYLOAD"""
        # Note: The _handle_payloads function is separate. This test only ensures
        # that parse_agent_response correctly separates the prose (with payload)
        # from the command.
        prose, command, prose_is_empty = parse_agent_response(response_text)
        expected_prose = """[2025-07-27 10:15:00] Here is the file content.

START @@PAYLOAD
print("Hello, World!")
END @@PAYLOAD"""
        self.assertEqual(prose.strip(), expected_prose.strip())
        self.assertIsNotNone(command)
        self.assertEqual(command['parameters']['content'], '@@PAYLOAD')

    def test_no_valid_json(self):
        """Tests a response that looks like it has JSON but doesn't, should be all prose."""
        response_text = "[2025-07-27 10:20:00] This is just text { with braces } but not JSON."
        prose, command, prose_is_empty = parse_agent_response(response_text)
        self.assertEqual(prose, response_text)
        self.assertIsNone(command)

    def test_empty_response(self):
        """Tests an empty string response."""
        response_text = ""
        prose, command, prose_is_empty = parse_agent_response(response_text)
        self.assertIsNone(prose)
        self.assertIsNone(command)
        self.assertTrue(prose_is_empty)

    def test_whitespace_response(self):
        """Tests a response with only whitespace."""
        response_text = "   \n\t   "
        prose, command, prose_is_empty = parse_agent_response(response_text)
        self.assertEqual(prose, "")
        self.assertIsNone(command)
        self.assertTrue(prose_is_empty)
        
    def test_prose_is_effectively_empty(self):
        """Tests a response where the prose is just a timestamp and whitespace."""
        response_text = """[2025-07-27 10:25:00]   
```json
{
    "action": "list_files"
}
```"""
        prose, command, prose_is_empty = parse_agent_response(response_text)
        self.assertEqual(prose, "[2025-07-27 10:25:00]")
        self.assertIsNotNone(command)
        self.assertTrue(prose_is_empty, "Prose should be considered effectively empty")


if __name__ == '__main__':
    # This allows the test to be run from the command line
    unittest.main(verbosity=2)
