# This script defines a series of strings to test the agent response parser.

test_cases = [
    # Test 1: Simple, correct case with prose and fenced JSON.
    (
        "This is a standard response. I will now list the directory.",
        '''```json
{
    "action": "list_directory",
    "parameters": {}
}
```'''
    ),

    # Test 2: Unfenced JSON. The brace counter should find this.
    (
        "This response has no JSON fences. Let's see if the brace counter works.",
        '''{
    "action": "list_directory",
    "parameters": {}
}'''
    ),

    # Test 3: Malformed but repairable JSON (unescaped newline in string).
    (
        "This JSON is slightly broken. The repair function should fix the newline in the content.",
        '''```json
{
    "action": "create_file",
    "parameters": {
        "filename": "test_newline.txt",
        "content": "This is a string with a
newline that needs fixing."
    }
}
```'''
    ),

    # Test 4: Multiple fenced JSON blocks. The parser should select the largest one.
    (
        "There are two JSON blocks here. The larger one should be chosen. The smaller one is a dummy.",
        '''```json
{
    "action": "respond",
    "parameters": {"response": "This is a dummy command."}
}
```
And now for the real command:
```json
{
    "action": "list_directory",
    "parameters": {
        "path": "./"
    }
}
```'''
    ),
    
    # Test 5: Standard payload/placeholder usage.
    (
        "This is a test of the payload system. I will create a file.",
        '''```json
{
	"action": "create_file", 
	"parameters": {
		"filename": "payload_test.txt", 
		"content": "@@PAYLOAD_CONTENT"
	}
}
```
START @@PAYLOAD_CONTENT
This is the content that should be extracted from the payload.
It can contain multiple lines.
END @@PAYLOAD_CONTENT'''
    ),
    
    # Test 6: Payload with complex content, including characters that might confuse a parser.
    # This is the key test for the new "mask-first" parsing logic.
    (
        "This payload contains tricky content to ensure the payload extractor is robust.",
        '''```json
{
	"action": "create_file", 
	"parameters": {
		"filename": "complex_payload.txt", 
		"content": "@@COMPLEX_PAYLOAD"
	}
}
```
START @@COMPLEX_PAYLOAD
{ "key": "This is not the command json" }
```json
This is also not the command.
```
This is the real content.
END @@COMPLEX_PAYLOAD'''
    ),

    # Test 7: JSON only, no prose, with fences.
    (
        "",
        '''```json
{
    "action": "list_directory",
    "parameters": {}
}
```'''
    ),

    # Test 8: Prose only, no JSON.
    (
        "This is just a simple text response. There is no command here, so the orchestrator should treat it as a final response.",
        ""
    ),
    
    # Test 9: Unrepairable JSON (e.g., trailing comma). Should be treated as prose.
    (
        "This JSON has a trailing comma, which is invalid and my repair function probably can't fix it. This whole message should be treated as prose.",
        '''```json
{
    "action": "list_directory",
    "parameters": {},
}
```'''
    )
]

# This part of the script will be used to print the test cases for the agent to use.
if __name__ == "__main__":
    for i, (prose, command) in enumerate(test_cases):
        print(f"----- TEST CASE {i+1} -----")
        # Combine prose and command into a single string, mimicking an agent response
        response = f"{prose}\n{command}".strip()
        print(response)
        print(f"----- END TEST CASE {i+1} -----\n")