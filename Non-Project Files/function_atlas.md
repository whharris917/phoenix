# Phoenix Project - Programmatically Generated Function Atlas

Generated from static code analysis of docstrings, type hints, and call relationships.

# FUNCTION DIRECTORY

## events.py

**events.replay_history_for_client** [🚀ENTRY ⚡CRITICAL 🔴HIGH-RISK]
  Parses raw chat history and emits granular rendering events to the client.
  `(socketio, session_id, session_name, history) -> None`
  Calls: 15 out, 0 in | Complexity: 30

**events._create_new_session** [🚀ENTRY ⚡CRITICAL 🔴HIGH-RISK]
  Creates a new user session and initializes all necessary components.
  `(session_id, proxy) -> ActiveSession`
  Calls: 6 out, 0 in | Complexity: 12

**events.register_events**
  Registers all SocketIO event handlers with the main application.
  `(socketio, haven_proxy)`
  Calls: 0 out, 1 in | Complexity: 1

**events.handle_connect** [🚀ENTRY ⚡CRITICAL 🔴HIGH-RISK]
  Handles a new client connection by creating and initializing a new session.
  `(auth) -> None`
  Calls: 6 out, 0 in | Complexity: 12

**events.handle_disconnect** [🚀ENTRY]
  Handles client disconnection by cleaning up session data.
  `(auth) -> None`
  Calls: 4 out, 0 in | Complexity: 8

**events.handle_start_task** [🚀ENTRY ⚡CRITICAL 🔴HIGH-RISK]
  Receives a task from the client and starts the agent's reasoning loop.
  `(data) -> None`
  Calls: 6 out, 0 in | Complexity: 12

**events.handle_session_list_request** [🚀ENTRY ⚡CRITICAL]
  Handles a client's request for the list of available sessions.
  `(auth) -> None`
  Calls: 5 out, 0 in | Complexity: 10

**events.handle_session_name_request**
  Handles a client's request for its current session name.
  `(auth) -> None`
  Calls: 3 out, 0 in | Complexity: 6

**events.handle_db_collections_request**
  Forwards a request for DB collections to the db_inspector.
  `(auth) -> None`
  Calls: 3 out, 0 in | Complexity: 6

**events.handle_db_collection_data_request** [🚀ENTRY]
  Forwards a request for specific collection data to the db_inspector.
  `(data) -> None`
  Calls: 4 out, 0 in | Complexity: 8

**events.handle_user_confirmation** [🚀ENTRY]
  Receives a 'yes' or 'no' from the user and forwards it to a waiting event.
  `(data) -> None`
  Calls: 4 out, 0 in | Complexity: 8

**events.handle_audit_log** [🚀ENTRY]
  Receives an audit log event from the client.
  `(data) -> None`
  Calls: 4 out, 0 in | Complexity: 8

**events.handle_get_trace_log** [🚀ENTRY]
  Handles a request from the scenario runner to get the trace log
  `(data)`
  Calls: 4 out, 0 in | Complexity: 8

**events.handle_get_haven_trace_log** [🚀ENTRY]
  Handles a request for the Haven service's trace log.
  `(data)`
  Calls: 4 out, 0 in | Complexity: 8

## haven.py

**haven.configure_logging**
  Configures the global logging settings for the Haven service.
  `() -> None`
  Calls: 1 out, 0 in | Complexity: 2

**haven.load_system_prompt** [🚀ENTRY]
  Loads the system prompt text from the 'system_prompt.txt' file.
  `() -> str`
  Calls: 4 out, 0 in | Complexity: 8

**haven.load_model_definition** [🚀ENTRY ⚡CRITICAL]
  Loads the model name from the 'model_definition.txt' file.
  `() -> str`
  Calls: 5 out, 0 in | Complexity: 10

**haven.initialize_model** [🚀ENTRY ⚡CRITICAL 🔴HIGH-RISK]
  Initializes the connection to Vertex AI and loads the generative model.
  `() -> Optional[GenerativeModel]`
  Calls: 6 out, 0 in | Complexity: 12

**haven.Haven.get_or_create_session** [🚀ENTRY ⚡CRITICAL]
  Gets a session history if it exists, otherwise creates a new one.
  `(self, session_name, history_dicts) -> bool`
  Calls: 5 out, 0 in | Complexity: 10

**haven.Haven.send_message** [🚀ENTRY ⚡CRITICAL 🔴HIGH-RISK]
  Sends a message by appending to the history and making a stateless
  `(self, session_name, prompt) -> dict[Tuple]`
  Calls: 6 out, 0 in | Complexity: 12

**haven.Haven.list_sessions**
  Returns a list of the names of all currently live sessions.
  `(self) -> list[str]`
  Calls: 2 out, 0 in | Complexity: 4

**haven.Haven.delete_session**
  Deletes a session from the live dictionary to free up memory.
  `(self, session_name) -> dict[Tuple]`
  Calls: 2 out, 0 in | Complexity: 4

**haven.Haven.has_session**
  Checks if a session exists in the Haven.
  `(self, session_name) -> bool`
  Calls: 0 out, 0 in | Complexity: 0

**haven.Haven.get_trace_log**
  Returns the trace log from this Haven process.
  `(self)`
  Calls: 1 out, 0 in | Complexity: 2

**haven.start_haven** [🚀ENTRY ⚡CRITICAL 🔴HIGH-RISK]
  Initializes and starts the Haven server process.
  `() -> None`
  Calls: 6 out, 0 in | Complexity: 12

## memory_manager.py

**memory_manager.initialize_embedding_function**
  Initializes the default sentence-transformer embedding model.
  `() -> Optional[embedding_functions.EmbeddingFunction]`
  Calls: 3 out, 0 in | Complexity: 6

**memory_manager.ChromaDBStore.__init__** [🚀ENTRY ⚡CRITICAL 🔴HIGH-RISK]
  Initializes the data store and connects to a ChromaDB collection.
  `(self, collection_name)`
  Calls: 9 out, 0 in | Complexity: 18

**memory_manager.ChromaDBStore.add_record**
  Adds a single MemoryRecord to the collection.
  `(self, record, record_id) -> None`
  Calls: 3 out, 0 in | Complexity: 6

**memory_manager.ChromaDBStore.get_all_records** [🚀ENTRY ⚡CRITICAL 🔴HIGH-RISK]
  Retrieves and validates all records from the collection, sorted by time.
  `(self) -> List[MemoryRecord]`
  Calls: 9 out, 0 in | Complexity: 18

**memory_manager.ChromaDBStore.query** [🚀ENTRY ⚡CRITICAL 🔴HIGH-RISK]
  Queries the collection for similar documents and returns validated records.
  `(self, query_text, n_results) -> List[MemoryRecord]`
  Calls: 10 out, 0 in | Complexity: 20

**memory_manager.ChromaDBStore.update_records_metadata**
  Updates metadata for existing records in the collection.
  `(self, ids, metadatas)`
  Calls: 2 out, 0 in | Complexity: 4

**memory_manager.ChromaDBStore.delete_collection** [🚀ENTRY]
  Deletes the entire collection from the database.
  `(self)`
  Calls: 4 out, 0 in | Complexity: 8

**memory_manager.MemoryManager.__init__**
  Initializes the memory manager for a specific session.
  `(self, session_name)`
  Calls: 2 out, 0 in | Complexity: 4

**memory_manager.MemoryManager._repopulate_buffer_from_db** [🚀ENTRY ⚡CRITICAL 🔴HIGH-RISK]
  Loads the most recent history from the DB into the conversational buffer.
  `(self)`
  Calls: 6 out, 0 in | Complexity: 12

**memory_manager.MemoryManager.add_turn** [🚀ENTRY ⚡CRITICAL 🔴HIGH-RISK]
  Adds a new turn to both the buffer (Tier 1) and vector store (Tier 2).
  `(self, role, content, metadata, augmented_prompt)`
  Calls: 13 out, 0 in | Complexity: 26

**memory_manager.MemoryManager.get_all_turns**
  Delegates retrieval of all turns to the data store.
  `(self) -> List[MemoryRecord]`
  Calls: 1 out, 0 in | Complexity: 2

**memory_manager.MemoryManager.get_context_for_prompt**
  Delegates context retrieval (vector search) to the data store.
  `(self, prompt, n_results) -> List[MemoryRecord]`
  Calls: 1 out, 0 in | Complexity: 2

**memory_manager.MemoryManager.get_conversational_buffer**
  Returns the short-term conversational buffer for the chat history.
  `(self) -> List[Content]`
  Calls: 0 out, 0 in | Complexity: 0

**memory_manager.MemoryManager.prepare_augmented_prompt** [🚀ENTRY]
  Retrieves relevant context from memory and constructs an augmented prompt.
  `(self, prompt) -> str`
  Calls: 4 out, 0 in | Complexity: 8

**memory_manager.MemoryManager.delete_memory_collection**
  Deletes the entire memory for the session from all data stores.
  `(self)`
  Calls: 3 out, 0 in | Complexity: 6

**memory_manager.MemoryManager.add_code_artifact** [🚀ENTRY]
  Saves a code artifact to a dedicated vector store and returns a pointer ID.
  `(self, filename, content) -> Optional[str]`
  Calls: 4 out, 0 in | Complexity: 8

## orchestrator.py

**orchestrator._emit_agent_message**
  A small wrapper to emit a formatted message to the client.
  `(socketio, session_id, message_type, content) -> None`
  Calls: 2 out, 0 in | Complexity: 4

**orchestrator._process_model_response**
  Parses raw model text into a structured ParsedAgentResponse object.
  `(response_text) -> ParsedAgentResponse`
  Calls: 3 out, 0 in | Complexity: 6

**orchestrator._render_agent_turn** [🚀ENTRY ⚡CRITICAL]
  Renders the agent's turn to the client from a ParsedAgentResponse object.
  `(socketio, session_id, parsed_response, is_live) -> None`
  Calls: 5 out, 0 in | Complexity: 10

**orchestrator.execute_reasoning_loop** [🚀ENTRY ⚡CRITICAL 🔴HIGH-RISK]
  Executes the main cognitive loop for the agent.
  `(socketio, session_data, initial_prompt, session_id, chat_sessions, haven_proxy) -> None`
  Calls: 21 out, 0 in | Complexity: 42

## phoenix.py

**phoenix.configure_servers** [🚀ENTRY]
  Initializes and configures the Flask and SocketIO servers and returns them
  `() -> Tuple[Tuple]`
  Calls: 4 out, 0 in | Complexity: 8

**phoenix.connect_to_haven** [🚀ENTRY ⚡CRITICAL 🔴HIGH-RISK]
  Establishes a connection to the Haven service with a retry loop.
  `() -> Optional[BaseManager]`
  Calls: 9 out, 0 in | Complexity: 18

**phoenix.initialize_services**
  Connects to the Haven service and registers all event handlers.
  `(socketio) -> Optional[BaseManager]`
  Calls: 2 out, 0 in | Complexity: 4

**phoenix.serve_index**
  Serves the main chat interface.
  Calls: 2 out, 0 in | Complexity: 4

**phoenix.serve_static_files**
  Serves static files like CSS and JS from the root directory.
  `(filename)`
  Calls: 2 out, 0 in | Complexity: 4

**phoenix.serve_audit_visualizer**
  Serves the audit log visualization tool.
  Calls: 2 out, 0 in | Complexity: 4

**phoenix.serve_database_viewer**
  Serves the ChromaDB inspection tool.
  Calls: 2 out, 0 in | Complexity: 4

**phoenix.serve_docs**
  Serves the documentation viewer.
  Calls: 2 out, 0 in | Complexity: 4

**phoenix.serve_markdown**
  Serves the raw markdown documentation file.
  Calls: 2 out, 0 in | Complexity: 4

**phoenix.serve_workshop**
  Serves the workshop/testing interface.
  Calls: 2 out, 0 in | Complexity: 4

## tool_agent.py

**tool_agent._execute_script** [🚀ENTRY ⚡CRITICAL 🔴HIGH-RISK]
  Executes a Python script in a restricted environment and captures its output.
  `(script_content) -> ToolResult`
  Calls: 6 out, 0 in | Complexity: 12

**tool_agent._write_file** [🚀ENTRY ⚡CRITICAL 🔴HIGH-RISK]
  Writes content to a file, creating directories if necessary.
  `(path, content) -> ToolResult`
  Calls: 7 out, 0 in | Complexity: 14

**tool_agent._read_file** [🚀ENTRY ⚡CRITICAL 🔴HIGH-RISK]
  Reads the content of a file.
  `(path) -> ToolResult`
  Calls: 6 out, 0 in | Complexity: 12

**tool_agent._delete_file** [🚀ENTRY ⚡CRITICAL]
  Deletes a file from the filesystem.
  `(path) -> ToolResult`
  Calls: 5 out, 0 in | Complexity: 10

**tool_agent._list_directory** [🚀ENTRY ⚡CRITICAL 🔴HIGH-RISK]
  Lists all files in a directory recursively, ignoring certain subdirectories.
  `(path) -> ToolResult`
  Calls: 7 out, 0 in | Complexity: 14

**tool_agent.get_safe_path** [🚀ENTRY ⚡CRITICAL 🔴HIGH-RISK]
  Constructs a safe file path within a designated directory, preventing path traversal.
  `(filename, base_dir_name) -> str`
  Calls: 6 out, 0 in | Complexity: 12

**tool_agent._extract_patch_paths** [🚀ENTRY]
  Extracts source (a) and target (b) filenames from a diff header.
  `(diff_content) -> tuple[Tuple]`
  Calls: 4 out, 0 in | Complexity: 8

**tool_agent._validate_patch_paths**
  Validates the source and target paths for the patch.
  `(source_filename, target_filename) -> ToolResult | None`
  Calls: 3 out, 0 in | Complexity: 6

**tool_agent._get_source_read_path** [🚀ENTRY ⚡CRITICAL]
  Determines the absolute path from which to read the source file.
  `(source_filename) -> str`
  Calls: 5 out, 0 in | Complexity: 10

**tool_agent._handle_create_file**
  Handles the 'create_file' action.
  `(params, context) -> ToolResult`
  Calls: 3 out, 0 in | Complexity: 6

**tool_agent._handle_read_file** [🚀ENTRY]
  Handles the 'read_file' action.
  `(params, context) -> ToolResult`
  Calls: 4 out, 0 in | Complexity: 8

**tool_agent._handle_read_project_file** [🚀ENTRY ⚡CRITICAL]
  Handles the 'read_project_file' action with validation.
  `(params, context) -> ToolResult`
  Calls: 5 out, 0 in | Complexity: 10

**tool_agent._handle_list_allowed_project_files**
  Handles the 'list_allowed_project_files' action.
  `(params, context) -> ToolResult`
  Calls: 1 out, 0 in | Complexity: 2

**tool_agent._handle_list_directory**
  Handles the 'list_directory' action.
  `(params, context) -> ToolResult`
  Calls: 2 out, 0 in | Complexity: 4

**tool_agent._handle_delete_file** [🚀ENTRY]
  Handles the 'delete_file' action.
  `(params, context) -> ToolResult`
  Calls: 4 out, 0 in | Complexity: 8

**tool_agent._handle_execute_python_script**
  Handles the 'execute_python_script' action.
  `(params, context) -> ToolResult`
  Calls: 2 out, 0 in | Complexity: 4

**tool_agent._handle_apply_patch** [🚀ENTRY ⚡CRITICAL 🔴HIGH-RISK]
  Orchestrates the 'apply_patch' action by calling decomposed helpers.
  `(params, context) -> ToolResult`
  Calls: 11 out, 0 in | Complexity: 22

**tool_agent._handle_list_sessions** [🚀ENTRY ⚡CRITICAL 🔴HIGH-RISK]
  Handles the 'list_sessions' action.
  `(params, context) -> ToolResult`
  Calls: 8 out, 0 in | Complexity: 16

**tool_agent._handle_load_session** [🚀ENTRY ⚡CRITICAL 🔴HIGH-RISK]
  Handles the 'load_session' action.
  `(params, context) -> ToolResult`
  Calls: 10 out, 0 in | Complexity: 20

**tool_agent._handle_save_session** [🚀ENTRY ⚡CRITICAL 🔴HIGH-RISK]
  Handles the 'save_session' action.
  `(params, context) -> ToolResult`
  Calls: 12 out, 0 in | Complexity: 24

**tool_agent._handle_delete_session** [🚀ENTRY ⚡CRITICAL 🔴HIGH-RISK]
  Handles the 'delete_session' action.
  `(params, context) -> ToolResult`
  Calls: 10 out, 0 in | Complexity: 20

**tool_agent.execute_tool_command** [🚀ENTRY ⚡CRITICAL]
  Executes a tool command by dispatching to the appropriate handler.
  `(command, socketio, session_id, chat_sessions, haven_proxy, loop_id) -> ToolResult`
  Calls: 5 out, 0 in | Complexity: 10


# HIERARCHICAL CALL TREES

## events._create_new_session
*Creates a new user session and initializes all necessary components.*
```
events._create_new_session [HIGH-RISK]
```

## events.handle_audit_log
*Receives an audit log event from the client.*
```
events.handle_audit_log
```

## events.handle_connect
*Handles a new client connection by creating and initializing a new session.*
```
events.handle_connect [HIGH-RISK]
```

## events.handle_db_collection_data_request
*Forwards a request for specific collection data to the db_inspector.*
```
events.handle_db_collection_data_request
```

## events.handle_disconnect
*Handles client disconnection by cleaning up session data.*
```
events.handle_disconnect
```

## events.handle_get_haven_trace_log
*Handles a request for the Haven service's trace log.*
```
events.handle_get_haven_trace_log
```

## events.handle_get_trace_log
*Handles a request from the scenario runner to get the trace log*
```
events.handle_get_trace_log
```

## events.handle_session_list_request
*Handles a client's request for the list of available sessions.*
```
events.handle_session_list_request [CRITICAL]
```

## events.handle_start_task
*Receives a task from the client and starts the agent's reasoning loop.*
```
events.handle_start_task [HIGH-RISK]
```

## events.handle_user_confirmation
*Receives a 'yes' or 'no' from the user and forwards it to a waiting event.*
```
events.handle_user_confirmation
```

## events.replay_history_for_client
*Parses raw chat history and emits granular rendering events to the client.*
```
events.replay_history_for_client [HIGH-RISK]
```

## haven.Haven.get_or_create_session
*Gets a session history if it exists, otherwise creates a new one.*
```
haven.Haven.get_or_create_session [CRITICAL]
```

## haven.Haven.send_message
*Sends a message by appending to the history and making a stateless*
```
haven.Haven.send_message [HIGH-RISK]
```

## haven.initialize_model
*Initializes the connection to Vertex AI and loads the generative model.*
```
haven.initialize_model [HIGH-RISK]
```

## haven.load_model_definition
*Loads the model name from the 'model_definition.txt' file.*
```
haven.load_model_definition [CRITICAL]
```

## haven.load_system_prompt
*Loads the system prompt text from the 'system_prompt.txt' file.*
```
haven.load_system_prompt
```

## haven.start_haven
*Initializes and starts the Haven server process.*
```
haven.start_haven [HIGH-RISK]
```

## memory_manager.ChromaDBStore.__init__
*Initializes the data store and connects to a ChromaDB collection.*
```
memory_manager.ChromaDBStore.__init__ [HIGH-RISK]
```

## memory_manager.ChromaDBStore.delete_collection
*Deletes the entire collection from the database.*
```
memory_manager.ChromaDBStore.delete_collection
```

## memory_manager.ChromaDBStore.get_all_records
*Retrieves and validates all records from the collection, sorted by time.*
```
memory_manager.ChromaDBStore.get_all_records [HIGH-RISK]
```

## memory_manager.ChromaDBStore.query
*Queries the collection for similar documents and returns validated records.*
```
memory_manager.ChromaDBStore.query [HIGH-RISK]
```

## memory_manager.MemoryManager._repopulate_buffer_from_db
*Loads the most recent history from the DB into the conversational buffer.*
```
memory_manager.MemoryManager._repopulate_buffer_from_db [HIGH-RISK]
```

## memory_manager.MemoryManager.add_code_artifact
*Saves a code artifact to a dedicated vector store and returns a pointer ID.*
```
memory_manager.MemoryManager.add_code_artifact
```

## memory_manager.MemoryManager.add_turn
*Adds a new turn to both the buffer (Tier 1) and vector store (Tier 2).*
```
memory_manager.MemoryManager.add_turn [HIGH-RISK]
```

## memory_manager.MemoryManager.prepare_augmented_prompt
*Retrieves relevant context from memory and constructs an augmented prompt.*
```
memory_manager.MemoryManager.prepare_augmented_prompt
```

## orchestrator._render_agent_turn
*Renders the agent's turn to the client from a ParsedAgentResponse object.*
```
orchestrator._render_agent_turn [CRITICAL]
```

## orchestrator.execute_reasoning_loop
*Executes the main cognitive loop for the agent.*
```
orchestrator.execute_reasoning_loop [HIGH-RISK]
```

## phoenix.configure_servers
*Initializes and configures the Flask and SocketIO servers and returns them*
```
phoenix.configure_servers
```

## phoenix.connect_to_haven
*Establishes a connection to the Haven service with a retry loop.*
```
phoenix.connect_to_haven [HIGH-RISK]
```

## tool_agent._delete_file
*Deletes a file from the filesystem.*
```
tool_agent._delete_file [CRITICAL]
```

## tool_agent._execute_script
*Executes a Python script in a restricted environment and captures its output.*
```
tool_agent._execute_script [HIGH-RISK]
```

## tool_agent._extract_patch_paths
*Extracts source (a) and target (b) filenames from a diff header.*
```
tool_agent._extract_patch_paths
```

## tool_agent._get_source_read_path
*Determines the absolute path from which to read the source file.*
```
tool_agent._get_source_read_path [CRITICAL]
```

## tool_agent._handle_apply_patch
*Orchestrates the 'apply_patch' action by calling decomposed helpers.*
```
tool_agent._handle_apply_patch [HIGH-RISK]
```

## tool_agent._handle_delete_file
*Handles the 'delete_file' action.*
```
tool_agent._handle_delete_file
```

## tool_agent._handle_delete_session
*Handles the 'delete_session' action.*
```
tool_agent._handle_delete_session [HIGH-RISK]
```

## tool_agent._handle_list_sessions
*Handles the 'list_sessions' action.*
```
tool_agent._handle_list_sessions [HIGH-RISK]
```

## tool_agent._handle_load_session
*Handles the 'load_session' action.*
```
tool_agent._handle_load_session [HIGH-RISK]
```

## tool_agent._handle_read_file
*Handles the 'read_file' action.*
```
tool_agent._handle_read_file
```

## tool_agent._handle_read_project_file
*Handles the 'read_project_file' action with validation.*
```
tool_agent._handle_read_project_file [CRITICAL]
```

## tool_agent._handle_save_session
*Handles the 'save_session' action.*
```
tool_agent._handle_save_session [HIGH-RISK]
```

## tool_agent._list_directory
*Lists all files in a directory recursively, ignoring certain subdirectories.*
```
tool_agent._list_directory [HIGH-RISK]
```

## tool_agent._read_file
*Reads the content of a file.*
```
tool_agent._read_file [HIGH-RISK]
```

## tool_agent._write_file
*Writes content to a file, creating directories if necessary.*
```
tool_agent._write_file [HIGH-RISK]
```

## tool_agent.execute_tool_command
*Executes a tool command by dispatching to the appropriate handler.*
```
tool_agent.execute_tool_command [CRITICAL]
```

## tool_agent.get_safe_path
*Constructs a safe file path within a designated directory, preventing path traversal.*
```
tool_agent.get_safe_path [HIGH-RISK]
```


# NAVIGATION GUIDE

## Bootstrap & Initialization
🔴 **phoenix.connect_to_haven**
   Establishes a connection to the Haven service with a retry loop.

🔴 **memory_manager.ChromaDBStore.__init__**
   Initializes the data store and connects to a ChromaDB collection.

🔴 **haven.start_haven**
   Initializes and starts the Haven server process.

🔴 **haven.initialize_model**
   Initializes the connection to Vertex AI and loads the generative model.

🔴 **events.handle_start_task**
   Receives a task from the client and starts the agent's reasoning loop.

## Client Communication
🔴 **events.replay_history_for_client**
   Parses raw chat history and emits granular rendering events to the client.

🔴 **tool_agent._handle_save_session**
   Handles the 'save_session' action.

🔴 **tool_agent._handle_apply_patch**
   Orchestrates the 'apply_patch' action by calling decomposed helpers.

🔴 **tool_agent._handle_load_session**
   Handles the 'load_session' action.

🔴 **tool_agent._handle_delete_session**
   Handles the 'delete_session' action.

## Core Logic & AI
🔴 **orchestrator.execute_reasoning_loop**
   Executes the main cognitive loop for the agent.

🔴 **tool_agent._write_file**
   Writes content to a file, creating directories if necessary.

🔴 **tool_agent._list_directory**
   Lists all files in a directory recursively, ignoring certain subdirectories.

🔴 **tool_agent.get_safe_path**
   Constructs a safe file path within a designated directory, preventing path traversal.

🔴 **tool_agent._read_file**
   Reads the content of a file.

## Data & Memory
🔴 **memory_manager.MemoryManager.add_turn**
   Adds a new turn to both the buffer (Tier 1) and vector store (Tier 2).

🔴 **memory_manager.ChromaDBStore.query**
   Queries the collection for similar documents and returns validated records.

🔴 **memory_manager.ChromaDBStore.get_all_records**
   Retrieves and validates all records from the collection, sorted by time.

🔴 **memory_manager.MemoryManager._repopulate_buffer_from_db**
   Loads the most recent history from the DB into the conversational buffer.

🟡 **memory_manager.MemoryManager.prepare_augmented_prompt**
   Retrieves relevant context from memory and constructs an augmented prompt.

## Utilities
🔴 **haven.Haven.send_message**
   Sends a message by appending to the history and making a stateless

🟡 **haven.Haven.get_or_create_session**
   Gets a session history if it exists, otherwise creates a new one.

🟡 **haven.load_system_prompt**
   Loads the system prompt text from the 'system_prompt.txt' file.

🟢 **phoenix.serve_workshop**
   Serves the workshop/testing interface.

🟢 **phoenix.serve_static_files**
   Serves static files like CSS and JS from the root directory.
