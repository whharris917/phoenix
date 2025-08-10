# Phoenix Code Atlas

## 🗺️ Structural Map: Modules & State
This section provides a high-level overview of each module, its primary purpose, and the state it manages.

### 📂 `audit_logger.py`
**Managed State:**
- `audit_log`: Assigned from `AuditLogger()`.

### 📂 `config.py`
**Managed State:**
- `PROJECT_ID`: Assigned from `'long-ratio-463815-n7'`.
- `LOCATION`: Assigned from `'us-east1'`.
- `SUMMARIZER_MODEL_NAME`: Assigned from `'gemini-2.0-flash-lite-001'`.
- `SEGMENT_THRESHOLD`: Assigned from `20`.
- `ABSOLUTE_MAX_ITERATIONS_REASONING_LOOP`: Assigned from `10`.
- `NOMINAL_MAX_ITERATIONS_REASONING_LOOP`: Assigned from `3`.
- `ALLOWED_PROJECT_FILES`: Assigned from `[...]`.
- `DEBUG_MODE`: Assigned from `False`.
- `SAFETY_SETTINGS`: Assigned from `{...}`.
- `CHROMA_DB_PATH`: Assigned from `os.path.join()`.
- `SERVER_PORT`: Assigned from `5001`.
- `HAVEN_ADDRESS`: Assigned from `<complex_value>`.
- `HAVEN_AUTH_KEY`: Assigned from `b'phoenixhaven'`.

### 📂 `data_models.py`
> *Defines the core data structures for the application using Pydantic.

This module provides centralized, validated models that ensure data consistency
across different components like the orchestrator, memory manager, tool agent,
and response parser. Using these models prevents common data-related errors
and makes the application's data flow explicit and self-documenting.*

### 📂 `distill_atlas.py`
### 📂 `events.py`
> *Defines the exclusive real-time communication bridge for the application.

This module serves as the secure "airlock" between the client-side user
interface and the backend application logic. It defines all SocketIO event
handlers, which are the only "levers" a user can pull to interact with the
system. It is responsible for session initialization, task delegation, and
forwarding all user requests to the appropriate backend components.

The core state is managed in the module-level 'chat_sessions' dictionary,
which maps client session IDs to their corresponding ActiveSession objects.*

**Managed State:**
- `chat_sessions`: Assigned from `{...}`.
- `_haven_proxy`: Assigned from `None`.

### 📂 `generate_code_atlas.py`
**Managed State:**
- `IGNORED_PREFIXES`: Assigned from `[...]`.
- `IGNORED_NAMES`: Assigned from `[...]`.

### 📂 `haven.py`
> *The Haven: A persistent, stateful service for managing AI model chat sessions.

This script runs as a separate, dedicated process. Its sole purpose is to hold the
expensive GenerativeModel object and all live chat histories in memory, safe
from the restarts and stateless nature of the main web application.

The core state is managed in the module-level 'live_chat_sessions' dictionary.
The main app connects to this service to send prompts and receive responses.*

**Managed State:**
- `model`: Assigned from `initialize_model()`.
- `live_chat_sessions`: Assigned from `{...}`.

### 📂 `inspect_db.py`
> *Provides direct database inspection and command-line interface (CLI) tools.

This module serves as a diagnostic and administrative utility for viewing the
contents of the ChromaDB vector store. It allows developers or advanced users
to directly query the database to list all collections (sessions) and view the
detailed memory records within them, bypassing the main application logic.

The functions in this module are primarily used by the 'Database Visualizer'
web page and the standalone CLI tool.*

### 📂 `memory_manager.py`
> *Manages the agent's memory, including conversational history and long-term
vector storage using ChromaDB.

This module implements a Tiered Memory Architecture:
- Tier 1: A short-term "working memory" in the form of a conversational buffer.
- Tier 2: A long-term, searchable "reference memory" in a ChromaDB vector store.

It encapsulates the logic for Retrieval-Augmented Generation (RAG) and provides
the main interface (MemoryManager) for the application to interact with memory.
The core state is the global 'embedding_function' used for all DB operations.*

**Managed State:**
- `embedding_function`: Assigned from `initialize_embedding_function()`.

### 📂 `orchestrator.py`
> *Core cognitive engine for the AI agent.

This module contains the primary reasoning loop that drives the agent's behavior.
It orchestrates the interaction between the agent's memory, the generative model,
and the tool execution system, forming the "brain" of the application.

The core state is managed in the module-level 'confirmation_events' dictionary,
which allows the reasoning loop to pause and wait for user input.*

**Managed State:**
- `confirmation_events`: Assigned from `{...}`.

### 📂 `patcher.py`
> *Provides a robust utility for applying agent-generated diff patches.

This module is designed to handle the complexities and common failure modes of
applying '.diff' files created by a generative model. Its primary function,
`apply_patch`, is a resilient wrapper that performs several crucial steps:
1. Normalizes text to prevent issues with line endings and special characters.
2. Intelligently corrects incorrect line numbers in hunk headers, which is a
   frequent error in agent-generated patches.
3. Applies the patch in a safe, temporary file system to prevent corrupting
   the original source files on failure.
4. Provides detailed error messages if a patch cannot be applied.*

### 📂 `phoenix.py`
> *Main application bootstrap file.

This script initializes the Flask application and the SocketIO server, connects
to the persistent Haven service, and registers the web routes and SocketIO
event handlers. It is responsible for starting the server and bringing all
components of the application online.*

**Managed State:**
- `haven_proxy`: Assigned from `initialize_services()`.

### 📂 `proxies.py`
> *Provides a client-side abstraction for interacting with the remote Haven service.

This module contains proxy wrappers that act as local stand-ins for remote
objects, simplifying the interaction between the main application and the
persistent Haven service. It ensures safe, session-aware communication and
abstracts away the details of the remote procedure calls.*

### 📂 `response_parser.py`
> *Provides robust parsing capabilities for converting raw LLM outputs into
structured data.

This module acts as a resilient "translation layer" between the unpredictable,
often messy, raw text generated by a large language model and the clean,
structured ParsedAgentResponse object that the rest of the application requires.
It is designed to handle common failure modes like mixed prose and JSON,
malformed JSON, and missing code fences.*

### 📂 `session_models.py`
> *Defines the high-level data structures for managing a user's session.

This module contains the Pydantic models that encapsulate the complete state
of a single, active user session, bundling together all the necessary service
proxies and managers required for the application's logic to operate.*

### 📂 `summarizer.py`
### 📂 `tool_agent.py`
> *Provides the secure action execution layer for the AI agent.

This module acts as the "hands" of the agent, providing the exclusive and
secure interface through which the agent can interact with the local system.
It is designed around a declarative, strategy-based pattern: the orchestrator
issues a command, and this module dispatches it to the appropriate handler
via the TOOL_REGISTRY.

All file system operations are strictly confined to a sandboxed directory to
ensure safety. Every tool execution returns a standardized ToolResult object,
providing a consistent data contract for the orchestrator.*

**Managed State:**
- `TOOL_REGISTRY`: Assigned from `{...}`.

### 📂 `tracer.py`
**Managed State:**
- `global_tracer`: Assigned from `Tracer()`.

### 📂 `utils.py`
> *Provides common, stateless utility functions used across the application.

This module is a collection of simple, reusable helper functions that do not
fit into a more specific module and have no external dependencies other than
standard Python libraries.*


---

## 🌳 Hierarchical Call Trees
This section visualizes the application's control flow, starting from 'root' functions (e.g., event handlers) that are not called by other functions within the project.

### ▶️ `audit_logger.AuditLogger.__init__`
```
└── audit_logger.AuditLogger.__init__
    ├── [new] threading.Lock
    └── audit_logger.AuditLogger._initialize_file
        └── writer.writerow
```

### ▶️ `audit_logger.AuditLogger.log_event`
```
└── audit_logger.AuditLogger.log_event
    ├── audit_logger.AuditLogger.socketio.start_background_task
    ├── audit_logger.serialize
    └── writer.writerow
```

### ▶️ `audit_logger.AuditLogger.register_socketio`
```
└── audit_logger.AuditLogger.register_socketio
```

### ▶️ `distill_atlas.distill_atlas`
```
└── distill_atlas.distill_atlas
    ├── distill_atlas.generate_call_trees
    │   ├── all_called_funcs.add
    │   ├── distill_atlas.build_tree_recursive
    │   │   ├── distill_atlas.build_tree_recursive (Circular Reference)
    │   │   ├── lines.extend
    │   │   ├── visited.add
    │   │   └── visited.copy
    │   └── markdown_lines.extend
    ├── distill_atlas.generate_structural_map
    └── f.write
```

### ▶️ `events.handle_audit_log`
```
└── events.handle_audit_log 💥 (accesses module state: chat_sessions)
    └── audit_logger.audit_log.log_event
```

### ▶️ `events.handle_connect`
```
└── events.handle_connect 💥 (accesses module state: _haven_proxy, chat_sessions)
    ├── events._create_new_session
    │   ├── [new] memory_manager.MemoryManager
    │   ├── [new] proxies.HavenProxyWrapper
    │   ├── [new] session_models.ActiveSession
    │   ├── object.get_or_create_session
    │   └── utils.get_timestamp
    │       └── upper
    ├── socketio.emit('log_message')
    ├── socketio.emit('session_config_update')
    └── socketio.emit('session_name_update')
```

### ▶️ `events.handle_db_collection_data_request`
```
└── events.handle_db_collection_data_request
    ├── inspect_db.get_collection_data_as_json
    │   ├── [new] memory_manager.ChromaDBStore
    │   ├── db_store.get_all_records
    │   └── formatted_data.sort
    └── socketio.emit('db_collection_data')
```

### ▶️ `events.handle_db_collections_request`
```
└── events.handle_db_collections_request
    ├── inspect_db.list_collections_as_json
    │   ├── client.list_collections
    │   ├── col.count
    │   ├── collection_list.sort
    │   └── inspect_db.get_db_client
    │       ├── [new] FileNotFoundError
    │       └── [new] chromadb.PersistentClient
    └── socketio.emit('db_collections_list')
```

### ▶️ `events.handle_disconnect`
```
└── events.handle_disconnect 💥 (accesses module state: chat_sessions)
```

### ▶️ `events.handle_get_haven_trace_log`
```
└── events.handle_get_haven_trace_log 💥 (accesses module state: _haven_proxy)
    ├── _haven_proxy.get_trace_log
    └── socketio.emit('haven_trace_log_response')
```

### ▶️ `events.handle_get_trace_log`
```
└── events.handle_get_trace_log
    ├── socketio.emit('trace_log_response')
    └── tracer.global_tracer.get_trace
```

### ▶️ `events.handle_session_list_request`
```
└── events.handle_session_list_request 💥 (accesses module state: _haven_proxy, chat_sessions)
    ├── [new] data_models.ToolCommand
    ├── socketio.emit('session_list_update')
    ├── tool_agent.execute_tool_command 💥 (accesses module state: TOOL_REGISTRY)
    │   ├── [new] data_models.ToolResult
    │   ├── [new] tool_agent.ToolContext
    │   └── handler
    └── tool_result.model_dump
```

### ▶️ `events.handle_session_name_request`
```
└── events.handle_session_name_request 💥 (accesses module state: chat_sessions)
    └── socketio.emit('session_name_update')
```

### ▶️ `events.handle_start_task`
```
└── events.handle_start_task 💥 (accesses module state: _haven_proxy, chat_sessions)
    ├── orchestrator.execute_reasoning_loop 💥 (accesses module state: confirmation_events)
    │   ├── [new] eventlet.event.Event
    │   ├── confirmation_event.wait
    │   ├── eventlet.tpool.execute
    │   ├── memory.add_turn
    │   ├── memory.prepare_augmented_prompt
    │   ├── orchestrator._process_model_response
    │   │   ├── [new] data_models.ToolCommand
    │   │   ├── response_parser._handle_payloads
    │   │   └── response_parser.parse_agent_response
    │   │       ├── [new] data_models.ParsedAgentResponse
    │   │       ├── data_models.ToolCommand.model_validate
    │   │       ├── response_parser._clean_prose
    │   │       ├── response_parser._extract_json_with_brace_counting
    │   │       │   ├── m.start
    │   │       │   └── response_parser._repair_json
    │   │       ├── response_parser._extract_json_with_fences
    │   │       ├── response_parser._mask_payloads
    │   │       ├── response_parser._repair_json
    │   │       └── response_parser.is_prose_effectively_empty
    │   ├── orchestrator._render_agent_turn
    │   │   ├── orchestrator._emit_agent_message
    │   │   │   └── socketio.emit('log_message')
    │   │   ├── response_parser.is_prose_effectively_empty
    │   │   └── socketio.emit('request_user_confirmation')
    │   ├── socketio.emit('log_message')
    │   ├── socketio.emit('tool_log')
    │   ├── tool_agent.execute_tool_command 💥 (accesses module state: TOOL_REGISTRY)
    │   │   ├── [new] data_models.ToolResult
    │   │   ├── [new] tool_agent.ToolContext
    │   │   └── handler
    │   ├── tool_result.model_dump_json
    │   └── utils.get_timestamp
    │       └── upper
    ├── socketio.emit('display_user_prompt')
    ├── socketio.emit('log_message')
    ├── socketio.start_background_task
    └── utils.get_timestamp
        └── upper
```

### ▶️ `events.handle_user_confirmation`
```
└── events.handle_user_confirmation
    └── event.send
```

### ▶️ `events.replay_history_for_client`
```
└── events.replay_history_for_client
    ├── data_models.ToolResult.model_validate
    ├── flask_socketio.SocketIO.emit
    ├── response_parser._handle_payloads
    └── response_parser.parse_agent_response
        ├── [new] data_models.ParsedAgentResponse
        ├── data_models.ToolCommand.model_validate
        ├── response_parser._clean_prose
        ├── response_parser._extract_json_with_brace_counting
        │   ├── m.start
        │   └── response_parser._repair_json
        ├── response_parser._extract_json_with_fences
        ├── response_parser._mask_payloads
        ├── response_parser._repair_json
        └── response_parser.is_prose_effectively_empty
```

### ▶️ `generate_code_atlas.CodeAnalyzer.__init__`
```
└── generate_code_atlas.CodeAnalyzer.__init__
```

### ▶️ `generate_code_atlas.CodeAnalyzer.analyze`
```
└── generate_code_atlas.CodeAnalyzer.analyze
    ├── ast.iter_child_nodes
    ├── ast.parse
    ├── ast.walk
    ├── generate_code_atlas.CodeAnalyzer.local_definitions.add
    ├── generate_code_atlas.CodeAnalyzer.local_definitions.clear
    ├── generate_code_atlas.CodeAnalyzer.module_state_names.add
    ├── generate_code_atlas.CodeAnalyzer.module_state_names.clear
    ├── generate_code_atlas.CodeAnalyzer.visit
    ├── getattr
    └── source.read
```

### ▶️ `generate_code_atlas.CodeAnalyzer.visit_AnnAssign`
```
└── generate_code_atlas.CodeAnalyzer.visit_AnnAssign
    ├── generate_code_atlas.CodeAnalyzer._get_value_repr
    │   └── generate_code_atlas._get_node_id
    │       └── generate_code_atlas._get_node_id (Circular Reference)
    └── generate_code_atlas.CodeAnalyzer.generic_visit
```

### ▶️ `generate_code_atlas.CodeAnalyzer.visit_Assign`
```
└── generate_code_atlas.CodeAnalyzer.visit_Assign
    ├── generate_code_atlas.CodeAnalyzer._get_value_repr
    │   └── generate_code_atlas._get_node_id
    │       └── generate_code_atlas._get_node_id (Circular Reference)
    └── generate_code_atlas.CodeAnalyzer.generic_visit
```

### ▶️ `generate_code_atlas.CodeAnalyzer.visit_ClassDef`
```
└── generate_code_atlas.CodeAnalyzer.visit_ClassDef
    ├── ast.get_docstring
    └── generate_code_atlas.CodeAnalyzer._get_function_details 💥 (accesses module state: IGNORED_NAMES, IGNORED_PREFIXES)
        ├── [new] generate_code_atlas.CallVisitor
        ├── ast.get_docstring
        ├── ast.walk
        ├── call_finder.visit
        ├── call_name_parts.insert
        ├── full_call_name.endswith
        ├── generate_code_atlas.CodeAnalyzer.accessed_state.add
        ├── generate_code_atlas.CodeAnalyzer.calls.add
        ├── generate_code_atlas.CodeAnalyzer.generic_visit
        ├── generate_code_atlas.CodeAnalyzer.instantiations.add
        ├── generate_code_atlas.CodeAnalyzer.passed_args.add
        └── generate_code_atlas._get_node_id
            └── generate_code_atlas._get_node_id (Circular Reference)
```

### ▶️ `generate_code_atlas.CodeAnalyzer.visit_FunctionDef`
```
└── generate_code_atlas.CodeAnalyzer.visit_FunctionDef
    ├── generate_code_atlas.CodeAnalyzer._get_function_details 💥 (accesses module state: IGNORED_NAMES, IGNORED_PREFIXES)
    │   ├── [new] generate_code_atlas.CallVisitor
    │   ├── ast.get_docstring
    │   ├── ast.walk
    │   ├── call_finder.visit
    │   ├── call_name_parts.insert
    │   ├── full_call_name.endswith
    │   ├── generate_code_atlas.CodeAnalyzer.accessed_state.add
    │   ├── generate_code_atlas.CodeAnalyzer.calls.add
    │   ├── generate_code_atlas.CodeAnalyzer.generic_visit
    │   ├── generate_code_atlas.CodeAnalyzer.instantiations.add
    │   ├── generate_code_atlas.CodeAnalyzer.passed_args.add
    │   └── generate_code_atlas._get_node_id
    │       └── generate_code_atlas._get_node_id (Circular Reference)
    ├── generate_code_atlas.CodeAnalyzer.generic_visit
    └── getattr
```

### ▶️ `generate_code_atlas.CodeAnalyzer.visit_Import`
```
└── generate_code_atlas.CodeAnalyzer.visit_Import
```

### ▶️ `generate_code_atlas.CodeAnalyzer.visit_ImportFrom`
```
└── generate_code_atlas.CodeAnalyzer.visit_ImportFrom
```

### ▶️ `generate_code_atlas.CodeAnalyzer.visit_Module`
```
└── generate_code_atlas.CodeAnalyzer.visit_Module
    ├── ast.get_docstring
    └── generate_code_atlas.CodeAnalyzer.generic_visit
```

### ▶️ `generate_code_atlas.generate_atlas`
```
└── generate_code_atlas.generate_atlas
    ├── [new] generate_code_atlas.CodeAnalyzer
    ├── analyzer.analyze
    ├── filename.endswith
    └── generate_code_atlas.refine_atlas_with_passed_args
        ├── all_defined_funcs.add
        └── generate_code_atlas.process_func_list
```

### ▶️ `haven.Haven.delete_session`
```
└── haven.Haven.delete_session 💥 (accesses module state: live_chat_sessions)
```

### ▶️ `haven.Haven.get_or_create_session`
```
└── haven.Haven.get_or_create_session 💥 (accesses module state: live_chat_sessions)
    ├── [new] vertexai.generative_models.Content
    └── vertexai.generative_models.Part.from_text
```

### ▶️ `haven.Haven.get_trace_log`
```
└── haven.Haven.get_trace_log
    └── tracer.global_tracer.get_trace
```

### ▶️ `haven.Haven.has_session`
```
└── haven.Haven.has_session 💥 (accesses module state: live_chat_sessions)
```

### ▶️ `haven.Haven.list_sessions`
```
└── haven.Haven.list_sessions 💥 (accesses module state: live_chat_sessions)
```

### ▶️ `haven.Haven.send_message`
```
└── haven.Haven.send_message 💥 (accesses module state: live_chat_sessions, model)
    ├── [new] vertexai.generative_models.Content
    ├── model.generate_content
    └── vertexai.generative_models.Part.from_text
```

### ▶️ `haven.configure_logging`
```
└── haven.configure_logging
```

### ▶️ `haven.initialize_model`
```
└── haven.initialize_model 💥 (accesses module state: model)
    ├── [new] vertexai.generative_models.GenerativeModel
    ├── haven.load_model_definition
    │   └── f.read
    ├── haven.load_system_prompt
    │   └── f.read
    └── vertexai.init
```

### ▶️ `haven.start_haven`
```
└── haven.start_haven
    ├── [new] haven.Haven
    ├── [new] haven.HavenManager
    ├── haven.HavenManager.register
    ├── manager.get_server
    └── server.serve_forever
```

### ▶️ `inspect_db.inspect_database_cli`
```
└── inspect_db.inspect_database_cli
    ├── [new] pandas.DataFrame
    ├── input
    ├── inspect_db.get_collection_data_as_json
    │   ├── [new] memory_manager.ChromaDBStore
    │   ├── db_store.get_all_records
    │   └── formatted_data.sort
    ├── inspect_db.list_collections_as_json
    │   ├── client.list_collections
    │   ├── col.count
    │   ├── collection_list.sort
    │   └── inspect_db.get_db_client
    │       ├── [new] FileNotFoundError
    │       └── [new] chromadb.PersistentClient
    ├── pandas.set_option
    └── traceback.print_exc
```

### ▶️ `memory_manager.ChromaDBStore.__init__`
```
└── memory_manager.ChromaDBStore.__init__ 💥 (accesses module state: embedding_function)
    ├── [new] chromadb.PersistentClient
    ├── c.isalnum
    └── chroma_client.get_or_create_collection
```

### ▶️ `memory_manager.ChromaDBStore.delete_collection`
```
└── memory_manager.ChromaDBStore.delete_collection
    ├── [new] chromadb.PersistentClient
    └── chroma_client.delete_collection
```

### ▶️ `memory_manager.ChromaDBStore.query`
```
└── memory_manager.ChromaDBStore.query
    ├── data_models.MemoryRecord.model_validate
    ├── memory_manager.ChromaDBStore.collection.count
    ├── memory_manager.ChromaDBStore.collection.query
    └── results_with_meta.sort
```

### ▶️ `memory_manager.ChromaDBStore.update_records_metadata`
```
└── memory_manager.ChromaDBStore.update_records_metadata
    └── memory_manager.ChromaDBStore.collection.update
```

### ▶️ `memory_manager.MemoryManager.__init__`
```
└── memory_manager.MemoryManager.__init__
    ├── [new] memory_manager.ChromaDBStore
    └── memory_manager.MemoryManager._repopulate_buffer_from_db
        ├── [new] vertexai.generative_models.Content
        ├── memory_manager.MemoryManager.turn_store.get_all_records
        └── vertexai.generative_models.Part.from_text
```

### ▶️ `memory_manager.MemoryManager.add_code_artifact`
```
└── memory_manager.MemoryManager.add_code_artifact
    ├── [new] data_models.MemoryRecord
    ├── memory_manager.MemoryManager.code_store.add_record
    └── time.time
```

### ▶️ `memory_manager.MemoryManager.add_turn`
```
└── memory_manager.MemoryManager.add_turn
    ├── [new] data_models.MemoryRecord
    ├── [new] vertexai.generative_models.Content
    ├── memory_manager.MemoryManager.turn_store.add_record
    ├── setattr
    ├── time.time
    └── vertexai.generative_models.Part.from_text
```

### ▶️ `memory_manager.MemoryManager.delete_memory_collection`
```
└── memory_manager.MemoryManager.delete_memory_collection
    ├── memory_manager.MemoryManager.code_store.delete_collection
    └── memory_manager.MemoryManager.turn_store.delete_collection
```

### ▶️ `memory_manager.MemoryManager.get_all_turns`
```
└── memory_manager.MemoryManager.get_all_turns
    └── memory_manager.MemoryManager.turn_store.get_all_records
```

### ▶️ `memory_manager.MemoryManager.get_conversational_buffer`
```
└── memory_manager.MemoryManager.get_conversational_buffer
```

### ▶️ `memory_manager.MemoryManager.prepare_augmented_prompt`
```
└── memory_manager.MemoryManager.prepare_augmented_prompt
    └── memory_manager.MemoryManager.get_context_for_prompt
        └── memory_manager.MemoryManager.turn_store.query
```

### ▶️ `memory_manager.initialize_embedding_function`
```
└── memory_manager.initialize_embedding_function 💥 (accesses module state: embedding_function)
    └── [new] chromadb.utils.embedding_functions.DefaultEmbeddingFunction
```

### ▶️ `phoenix.configure_servers`
```
└── phoenix.configure_servers
    ├── [new] flask.Flask
    ├── [new] flask_cors.CORS
    └── [new] flask_socketio.SocketIO
```

### ▶️ `phoenix.initialize_services`
```
└── phoenix.initialize_services 💥 (accesses module state: haven_proxy)
    ├── events.register_events 💥 (accesses module state: _haven_proxy, chat_sessions)
    │   ├── [new] data_models.ToolCommand
    │   ├── _haven_proxy.get_trace_log
    │   ├── audit_logger.audit_log.log_event
    │   ├── event.send
    │   ├── events._create_new_session
    │   │   ├── [new] memory_manager.MemoryManager
    │   │   ├── [new] proxies.HavenProxyWrapper
    │   │   ├── [new] session_models.ActiveSession
    │   │   ├── object.get_or_create_session
    │   │   └── utils.get_timestamp
    │   │       └── upper
    │   ├── flask_socketio.SocketIO.emit
    │   ├── flask_socketio.SocketIO.on
    │   ├── flask_socketio.SocketIO.start_background_task
    │   ├── inspect_db.get_collection_data_as_json
    │   │   ├── [new] memory_manager.ChromaDBStore
    │   │   ├── db_store.get_all_records
    │   │   └── formatted_data.sort
    │   ├── inspect_db.list_collections_as_json
    │   │   ├── client.list_collections
    │   │   ├── col.count
    │   │   ├── collection_list.sort
    │   │   └── inspect_db.get_db_client
    │   │       ├── [new] FileNotFoundError
    │   │       └── [new] chromadb.PersistentClient
    │   ├── orchestrator.execute_reasoning_loop 💥 (accesses module state: confirmation_events)
    │   │   ├── [new] eventlet.event.Event
    │   │   ├── confirmation_event.wait
    │   │   ├── eventlet.tpool.execute
    │   │   ├── memory.add_turn
    │   │   ├── memory.prepare_augmented_prompt
    │   │   ├── orchestrator._process_model_response
    │   │   │   ├── [new] data_models.ToolCommand
    │   │   │   ├── response_parser._handle_payloads
    │   │   │   └── response_parser.parse_agent_response
    │   │   │       ├── [new] data_models.ParsedAgentResponse
    │   │   │       ├── data_models.ToolCommand.model_validate
    │   │   │       ├── response_parser._clean_prose
    │   │   │       ├── response_parser._extract_json_with_brace_counting
    │   │   │       │   ├── m.start
    │   │   │       │   └── response_parser._repair_json
    │   │   │       ├── response_parser._extract_json_with_fences
    │   │   │       ├── response_parser._mask_payloads
    │   │   │       ├── response_parser._repair_json
    │   │   │       └── response_parser.is_prose_effectively_empty
    │   │   ├── orchestrator._render_agent_turn
    │   │   │   ├── orchestrator._emit_agent_message
    │   │   │   │   └── socketio.emit('log_message')
    │   │   │   ├── response_parser.is_prose_effectively_empty
    │   │   │   └── socketio.emit('request_user_confirmation')
    │   │   ├── socketio.emit('log_message')
    │   │   ├── socketio.emit('tool_log')
    │   │   ├── tool_agent.execute_tool_command 💥 (accesses module state: TOOL_REGISTRY)
    │   │   │   ├── [new] data_models.ToolResult
    │   │   │   ├── [new] tool_agent.ToolContext
    │   │   │   └── handler
    │   │   ├── tool_result.model_dump_json
    │   │   └── utils.get_timestamp
    │   │       └── upper
    │   ├── tool_agent.execute_tool_command 💥 (accesses module state: TOOL_REGISTRY)
    │   │   ├── [new] data_models.ToolResult
    │   │   ├── [new] tool_agent.ToolContext
    │   │   └── handler
    │   ├── tool_result.model_dump
    │   ├── tracer.global_tracer.get_trace
    │   └── utils.get_timestamp
    │       └── upper
    └── phoenix.connect_to_haven
        ├── [new] phoenix.HavenManager
        ├── manager.connect
        ├── manager.get_haven
        └── phoenix.HavenManager.register
```

### ▶️ `phoenix.serve_audit_visualizer`
```
└── phoenix.serve_audit_visualizer
    └── flask.send_from_directory
```

### ▶️ `phoenix.serve_database_viewer`
```
└── phoenix.serve_database_viewer
    └── flask.send_from_directory
```

### ▶️ `phoenix.serve_docs`
```
└── phoenix.serve_docs
    └── flask.send_from_directory
```

### ▶️ `phoenix.serve_index`
```
└── phoenix.serve_index
    └── flask.send_from_directory
```

### ▶️ `phoenix.serve_markdown`
```
└── phoenix.serve_markdown
    └── flask.send_from_directory
```

### ▶️ `phoenix.serve_static_files`
```
└── phoenix.serve_static_files
    └── flask.send_from_directory
```

### ▶️ `phoenix.serve_workshop`
```
└── phoenix.serve_workshop
    └── flask.send_from_directory
```

### ▶️ `proxies.HavenProxyWrapper.__init__`
```
└── proxies.HavenProxyWrapper.__init__
```

### ▶️ `proxies.HavenProxyWrapper.send_message`
```
└── proxies.HavenProxyWrapper.send_message
    ├── [new] RuntimeError
    ├── [new] proxies.MockResponse
    └── proxies.HavenProxyWrapper.haven.send_message
```

### ▶️ `summarizer.main`
```
└── summarizer.main
    ├── [new] chromadb.PersistentClient
    ├── [new] data_models.MemoryRecord
    ├── [new] memory_manager.ChromaDBStore
    ├── [new] vertexai.generative_models.GenerativeModel
    ├── chroma_client.list_collections
    ├── cutoff_date.timestamp
    ├── db_store.add_record
    ├── db_store.get_all_records
    ├── db_store.update_records_metadata
    ├── record.model_copy
    ├── summarizer_model.generate_content
    ├── time.time
    ├── updated_record.model_dump
    ├── vertexai.generative_models.Part.from_text
    └── vertexai.init
```

### ▶️ `tool_agent._handle_apply_patch`
```
└── tool_agent._handle_apply_patch
    ├── [new] data_models.ToolResult
    ├── eventlet.tpool.execute
    ├── patcher.apply_patch
    │   ├── corrected_diff.encode
    │   ├── corrected_diff.endswith
    │   ├── f.read
    │   ├── f.write
    │   ├── new_content.rstrip
    │   ├── patch.fromstring
    │   ├── patch_set.apply
    │   ├── patcher._correct_hunk_line_numbers
    │   │   └── corrected_diff_lines.extend
    │   ├── patcher._normalize_text
    │   │   └── text.rstrip
    │   ├── shutil.rmtree
    │   └── tempfile.mkdtemp
    ├── tool_agent._extract_patch_paths
    ├── tool_agent._get_source_read_path
    │   └── tool_agent.get_safe_path
    │       └── [new] ValueError
    ├── tool_agent._read_file
    │   ├── [new] data_models.ToolResult
    │   └── f.read
    ├── tool_agent._validate_patch_paths
    │   └── [new] data_models.ToolResult
    ├── tool_agent._write_file
    │   ├── [new] data_models.ToolResult
    │   └── f.write
    └── tool_agent.get_safe_path
        └── [new] ValueError
```

### ▶️ `tool_agent._handle_create_file`
```
└── tool_agent._handle_create_file
    ├── eventlet.tpool.execute
    ├── tool_agent._write_file
    │   ├── [new] data_models.ToolResult
    │   └── f.write
    └── tool_agent.get_safe_path
        └── [new] ValueError
```

### ▶️ `tool_agent._handle_delete_file`
```
└── tool_agent._handle_delete_file
    ├── [new] data_models.ToolResult
    ├── eventlet.tpool.execute
    ├── tool_agent._delete_file
    │   └── [new] data_models.ToolResult
    └── tool_agent.get_safe_path
        └── [new] ValueError
```

### ▶️ `tool_agent._handle_delete_session`
```
└── tool_agent._handle_delete_session
    ├── ToolContext.haven_proxy.delete_session
    ├── ToolContext.socketio.emit('session_list_update')
    ├── [new] data_models.ToolResult
    ├── [new] memory_manager.ChromaDBStore
    ├── code_store.delete_collection
    ├── tool_agent._handle_list_sessions
    │   ├── ToolContext.haven_proxy.list_sessions
    │   ├── [new] chromadb.PersistentClient
    │   ├── [new] data_models.ToolResult
    │   ├── chroma_client.list_collections
    │   └── session_list.sort
    ├── turn_store.delete_collection
    └── updated_list_result.model_dump
```

### ▶️ `tool_agent._handle_execute_python_script`
```
└── tool_agent._handle_execute_python_script
    ├── eventlet.tpool.execute
    └── tool_agent._execute_script
        ├── [new] data_models.ToolResult
        ├── [new] io.StringIO
        ├── contextlib.redirect_stdout
        ├── exec
        └── string_io.getvalue
```

### ▶️ `tool_agent._handle_list_allowed_project_files`
```
└── tool_agent._handle_list_allowed_project_files
    └── [new] data_models.ToolResult
```

### ▶️ `tool_agent._handle_list_directory`
```
└── tool_agent._handle_list_directory
    ├── eventlet.tpool.execute
    ├── tool_agent._list_directory
    │   └── [new] data_models.ToolResult
    └── tool_agent.get_safe_path
        └── [new] ValueError
```

### ▶️ `tool_agent._handle_load_session`
```
└── tool_agent._handle_load_session
    ├── ToolContext.haven_proxy.get_or_create_session
    ├── ToolContext.socketio.emit('session_name_update')
    ├── [new] data_models.ToolResult
    ├── [new] memory_manager.ChromaDBStore
    ├── [new] memory_manager.MemoryManager
    ├── [new] proxies.HavenProxyWrapper
    ├── [new] session_models.ActiveSession
    ├── memory_manager.ChromaDBStore.get_all_records
    │   ├── all_records.sort
    │   ├── data_models.MemoryRecord.model_validate
    │   └── memory_manager.ChromaDBStore.collection.count
    └── replay_history_for_client
```

### ▶️ `tool_agent._handle_read_file`
```
└── tool_agent._handle_read_file
    ├── [new] data_models.ToolResult
    ├── eventlet.tpool.execute
    ├── tool_agent._read_file
    │   ├── [new] data_models.ToolResult
    │   └── f.read
    └── tool_agent.get_safe_path
        └── [new] ValueError
```

### ▶️ `tool_agent._handle_read_project_file`
```
└── tool_agent._handle_read_project_file
    ├── [new] data_models.ToolResult
    ├── eventlet.tpool.execute
    └── tool_agent._read_file
        ├── [new] data_models.ToolResult
        └── f.read
```

### ▶️ `tool_agent._handle_save_session`
```
└── tool_agent._handle_save_session
    ├── ToolContext.haven_proxy.get_or_create_session
    ├── ToolContext.socketio.emit('session_name_update')
    ├── [new] data_models.ToolResult
    ├── [new] memory_manager.ChromaDBStore
    ├── [new] proxies.HavenProxyWrapper
    ├── memory_manager.ChromaDBStore.add_record
    │   ├── data_models.MemoryRecord.model_dump
    │   └── memory_manager.ChromaDBStore.collection.add
    └── memory_manager.ChromaDBStore.get_all_records
        ├── all_records.sort
        ├── data_models.MemoryRecord.model_validate
        └── memory_manager.ChromaDBStore.collection.count
```

### ▶️ `tracer.Tracer.__init__`
```
└── tracer.Tracer.__init__
    └── tracer.Tracer.reset
```

### ▶️ `tracer.Tracer.end_trace`
```
└── tracer.Tracer.end_trace
    └── tracer._sanitize_repr
```

### ▶️ `tracer.Tracer.get_trace`
```
└── tracer.Tracer.get_trace
    └── tracer._clean_trace_log
        └── tracer._clean_trace_log (Circular Reference)
```

### ▶️ `tracer.Tracer.start_trace`
```
└── tracer.Tracer.start_trace
```

### ▶️ `tracer.log_event`
```
└── tracer.log_event 💥 (accesses module state: global_tracer)
    └── inspect.stack
```

### ▶️ `tracer.trace`
```
└── tracer.trace 💥 (accesses module state: global_tracer)
    ├── func
    ├── functools.wraps
    ├── global_tracer.end_trace
    ├── global_tracer.start_trace
    └── inspect.getfile
```

### ▶️ `tracer.wrapper`
```
└── tracer.wrapper 💥 (accesses module state: global_tracer)
    ├── func
    ├── global_tracer.end_trace
    ├── global_tracer.start_trace
    └── inspect.getfile
```
