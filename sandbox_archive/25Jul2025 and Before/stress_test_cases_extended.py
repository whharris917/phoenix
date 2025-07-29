# This script defines a second, more challenging series of strings to stress test the agent response parser.

extended_test_cases = [
    # Test 10: Multiple Payloads, one containing a decoy JSON object.
    # Purpose: Verifies that _mask_payloads runs first, preventing the JSON extractor from seeing the decoy.
    (
        "This response has two payloads. The first contains a decoy JSON. The command uses the second payload.",
        '''```json
{
	"action": "create_file",
	"parameters": {
		"filename": "test_10.txt",
		"content": "@@REAL_CONTENT"
	}
}
```
START @@DECOY_PAYLOAD
{ "action": "this_should_be_ignored", "parameters": {} }
END @@DECOY_PAYLOAD

START @@REAL_CONTENT
This is the actual file content for test 10.
END @@REAL_CONTENT'''
    ),

    # Test 11: A payload placeholder name appears in the prose but isn't a real placeholder.
    # Purpose: Ensures the payload handler doesn't get confused by incidental "@@" strings.
    (
        "My email is test@@example.com. Now, please create a file.",
        '''```json
{
    "action": "create_file",
    "parameters": {
        "filename": "test_11.txt",
        "content": "This is a simple test."
    }
}
```'''
    ),

    # Test 12: Malformed payload markers (mismatched END).
    # Purpose: Checks for robust failure. The payload extraction should fail, but the system shouldn't crash.
    # The tool will likely receive the literal string "@@BROKEN_MARKER".
    (
        "This payload has a mismatched end marker.",
        '''```json
{
	"action": "create_file",
	"parameters": {
		"filename": "test_12.txt",
		"content": "@@BROKEN_MARKER"
	}
}
```
START @@BROKEN_MARKER
This content should not be extracted.
END @@BROKN_MARKER'''
    ),

    # Test 13: Adjacent payloads for a single command.
    # Purpose: Verifies that the parser can handle multiple placeholders and adjacent START/END blocks.
    (
        "This command uses two adjacent payloads.",
        '''```json
{
	"action": "create_file",
	"parameters": {
		"filename": "@@FILENAME_13",
		"content": "@@CONTENT_13"
	}
}
```
START @@FILENAME_13
test_13_adjacent.txt
END @@FILENAME_13
START @@CONTENT_13
This content comes from the second of two adjacent payloads.
END @@CONTENT_13'''
    ),

    # Test 14: JSON with comments.
    # Purpose: This is invalid JSON. The parser should reject it and treat the whole response as prose.
    (
        "This JSON contains comments, which are not allowed. It should be treated as prose.",
        '''```json
{
    // This is a comment that should break the parser.
    "action": "list_directory",
    "parameters": {}
}
```'''
    ),

    # Test 15: Valid JSON with escaped characters.
    # Purpose: A sanity check to ensure standard escaping doesn't cause issues.
    (
        "This test includes a string with escaped quotes and backslashes.",
        '''```json
{
    "action": "create_file",
    "parameters": {
        "filename": "test_15_escaped.txt",
        "content": "Here is a string with \\"escaped quotes\\" and a literal backslash: \\\\."
    }
}
```'''
    ),
    
    # Test 16: Empty payload content.
    # Purpose: Ensures that an empty payload block results in an empty string value for the parameter.
    (
        "Creating a file with an empty payload.",
        '''```json
{
	"action": "create_file",
	"parameters": {
		"filename": "test_16_empty.txt",
		"content": "@@EMPTY_PAYLOAD"
	}
}
```
START @@EMPTY_PAYLOAD
END @@EMPTY_PAYLOAD'''
    ),

    # Test 17: Noisy JSON fences (text inside the fences but outside the braces).
    # Purpose: The regex for fenced JSON should be specific enough to only extract the {...} object.
    (
        "The JSON block below has extra text inside the fences that should be ignored.",
        '''```json
This text is noise and should be ignored by the JSON extractor.
{
    "action": "list_directory",
    "parameters": { "comment": "Test 17" }
}
This text is also noise.
```'''
    ),

    # Test 18: Decoy unfenced JSON appearing before the real fenced command.
    # Purpose: Confirms that the fence-based extractor has priority over the brace-counting fallback.
    (
        "Here is a decoy JSON object: { \"decoy\": true, \"comment\": \"This should be ignored.\" }. Now for the real command:",
        '''```json
{
    "action": "list_directory",
    "parameters": { "comment": "Test 18" }
}
```'''
    ),

    # Test 19: Mismatched braces in prose to confuse the brace-counter.
    # Purpose: If the primary fence extractor fails, this tests the robustness of the brace-counting fallback.
    (
        "Here are some stray braces { { } to try and confuse the parser. The real command is unfenced:",
        '''
{
    "action": "list_directory",
    "parameters": { "comment": "Test 19" }
}'''
    ),

    # Test 20: Comprehensive "Final Boss" test.
    # Purpose: Combines multiple failure points to ensure the final logic is sound.
    (
        "Final test. Here's a decoy object { \"a\": 1 }. Here's a decoy payload.",
        '''```json
{
    "action": "create_file",
    "parameters": {
        "filename": "test_20_final.txt",
        "content": "@@FINAL_CONTENT"
    }
}
```
START @@DECOY_PAYLOAD_20
This payload contains yet another decoy: { "action": "ignore_me" }
END @@DECOY_PAYLOAD_20

Some prose between payloads.

START @@FINAL_CONTENT
This is the real content for the final test.
END @@FINAL_CONTENT
'''
    )
]

if __name__ == "__main__":
    for i, (prose, command) in enumerate(extended_test_cases):
        print(f"----- EXTENDED TEST CASE {i+10} -----")
        response = f"{prose}\n{command}".strip()
        print(response)
        print(f"----- END TEST CASE -----\n")