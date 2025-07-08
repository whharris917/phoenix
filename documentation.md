# Introduction

This document provides a high-level overview of the Gemini Local Agent project. The system is designed to allow a user to interact with their local file system through a natural language interface, powered by Google's Gemini model. The architecture is split into distinct, modular components to ensure security, readability, and a responsive user experience.

---

## System Architecture

The project follows a multi-tier architecture consolidated into a single server application (`app.py`) for ease of use. The application is logically divided into three main components:

1. **Front-End (UI)**: A web-based interface where the user interacts with the system.

2. **Orchestrator**: The reasoning engine that communicates with the Gemini API to plan tasks.

3. **Tool Agent**: The execution engine that performs safe, sandboxed actions on the local machine.

---

## Component Breakdown

### 1. Main Server (`app.py`)

This is the central entry point of the application. Its primary role is to handle web requests, manage real-time WebSocket connections, and wire the other components together.

* **Key Functions/Routes**:

  * `serve_index()`, `serve_docs()`: Standard Flask routes to serve the HTML and Markdown files to the browser.

  * `handle_connect()`, `handle_disconnect()`: SocketIO event handlers that manage the lifecycle of a user's connection. They are responsible for creating and destroying a user's unique `chat` session object.

  * `handle_start_task(data)`: The main SocketIO event handler. When it receives a prompt from the UI, it retrieves the correct `chat` session and starts the reasoning loop in the orchestrator as a background task.

    * **Objects Passed**: It passes the `socketio` object, the user's `chat` object, the `prompt` string, the `session_id`, and the global `chat_sessions` and `model` objects to the `execute_reasoning_loop`.

### 2. Orchestrator (`orchestrator.py`)

This module is the "brain" of the operation. It contains the logic for the agent's reasoning process.

* **Key Functions/Methods**:

  * `execute_reasoning_loop(...)`: This function contains the primary loop for agent interaction. It takes the user's prompt and sends it to the Gemini API. Based on the API's response, it decides whether to call a tool or return a final answer.

    * **Receives**: The `socketio` object (for sending messages back to the UI), the `chat` object (to maintain conversation history), and the user's `prompt`.

    * **Calls**: `chat.send_message()` to communicate with the Gemini API.

    * **Calls**: `execute_tool_command()` from the `tool_agent` module when Gemini decides to use a tool.

    * **Data Flow**: It passes the `command_json` received from Gemini into the `execute_tool_command` function and sends the `tool_result` back to the Gemini API for the next step in the loop.

### 3. Tool Agent (`tool_agent.py`)

This module is the "hands" of the operation, containing a library of functions that can perform actions on the local system. It is designed to be completely isolated and secure.

* **Key Functions/Methods**:

  * `execute_tool_command(command, ...)`: A central dispatcher function that takes a JSON command from the Orchestrator and calls the appropriate internal function based on the `"action"` key.

    * **Receives**: A `command` dictionary (JSON object).

    * **Returns**: A result dictionary (JSON object) indicating the status and outcome of the action.

  * `create_file()`, `read_file()`, `delete_file()`, etc.: Each of these functions performs one specific, safe action within the `sandbox` directory. They contain security checks (like `get_safe_path`) to prevent any access outside the designated containment zone.

---

## Data Flow: A Step-by-Step Example

Consider the prompt: *Delete the file named 'old_report.txt'.*

 1. **User Input**: The user types the prompt into `index.html`.

 2. **UI to `app.py`**: The UI sends a `start_task` event with the prompt string over WebSocket.

 3. **`app.py` to `orchestrator.py`**: The `handle_start_task` function in `app.py` calls `execute_reasoning_loop` in `orchestrator.py`, passing the `chat` object and the prompt.

 4. **`orchestrator.py` to Gemini**: The orchestrator sends the prompt to the Gemini API. Gemini, following its safety instructions, responds with a JSON command: `{"action": "request_confirmation", "parameters": {"prompt": "Are you sure...?"}}`.

 5. **`orchestrator.py` to UI**: The orchestrator receives this command and emits a `request_user_confirmation` event to the UI, then pauses.

 6. **User to UI to `app.py`**: The user clicks "Yes". The UI sends a `user_confirmation` event to `app.py`.

 7. **`app.py` to `orchestrator.py`**: The `handle_user_confirmation` function "wakes up" the paused `execute_reasoning_loop`.

 8. **`orchestrator.py` to Gemini**: The orchestrator sends the confirmation result ("USER_CONFIRMATION: 'yes'") to the Gemini API. Gemini now responds with the `delete_file` command.

 9. **`orchestrator.py` to `tool_agent.py`**: The orchestrator calls the `execute_tool_command` function in `tool_agent.py`, passing the `delete_file` JSON.

10. **`tool_agent.py` Execution**: The tool agent logic deletes the file from the sandbox and returns a success message.

11. **Final Answer**: The result is passed back up the chain, and the orchestrator sends a final confirmation message to the UI.