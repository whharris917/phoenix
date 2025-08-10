# Unified Code Atlas - Generated Analysis

## ==================================================
orchestrator - 
Core cognitive engine for the AI agent.

This module contains the primary reasoning loop that drives the agent's behavior.
It orchestrates the interaction between the agent's memory, the generative model,
and the tool execution system, forming the "brain" of the application.

The core state is managed in the module-level 'confirmation_events' dictionary,
which allows the reasoning loop to pause and wait for user input.


Functions:
  _emit_agent_message()
    @calls: content.strip, socketio.emit
    @creates: str
    @returns: None

  _process_model_response()
    @calls: ToolCommand, _handle_payloads, parse_agent_response
    @returns: ParsedAgentResponse

  _render_agent_turn()
    @calls: _emit_agent_message, command.parameters.get, is_prose_effectively_empty, len, socketio.emit
    @returns: None

  execute_reasoning_loop()
    @calls: Event, _process_model_response, _render_agent_turn, confirmation_event.wait, confirmation_events.pop, execute_tool_command, get_timestamp, json.dumps, logging.exception, logging.info, logging.warning, memory.add_turn, memory.prepare_augmented_prompt, range, re.match, socketio.emit, socketio.sleep, str, tool_result.model_dump_json, tpool.execute, uuid.uuid4
    @creates: str, uuid.uuid4
    @returns: None


## ==================================================
tool_agent - 
Provides the secure action execution layer for the AI agent.

This module acts as the "hands" of the agent, providing the exclusive and
secure interface through which the agent can interact with the local system.
It is designed around a declarative, strategy-based pattern: the orchestrator
issues a command, and this module dispatches it to the appropriate handler
via the TOOL_REGISTRY.

All file system operations are strictly confined to a sandboxed directory to
ensure safety. Every tool execution returns a standardized ToolResult object,
providing a consistent data contract for the orchestrator.


Functions:
  _execute_script()
    @calls: ToolResult, exec, io.StringIO, redirect_stdout, str, string_io.getvalue
    @creates: str
    @returns: ToolResult

  _write_file()
    @calls: ToolResult, f.write, open, os.makedirs, os.path.basename, os.path.dirname, str
    @creates: str
    @returns: ToolResult

  _read_file()
    @calls: ToolResult, f.read, open, os.path.basename, os.path.exists, str
    @creates: str
    @returns: ToolResult

  _delete_file()
    @calls: ToolResult, os.path.basename, os.path.exists, os.remove, str
    @creates: str
    @returns: ToolResult

  _list_directory()
    @calls: ToolResult, file_list.append, os.path.join, os.path.relpath, os.walk, relative_path.replace, str
    @creates: list, str
    @returns: ToolResult

  get_safe_path()
    @calls: ValueError, os.makedirs, os.path.abspath, os.path.dirname, os.path.join, requested_path.startswith
    @returns: str

  _extract_patch_paths()
    @calls: Subscript.strip, diff_content.splitlines, line.split, line.startswith
    @creates: str
    @returns: Subscript

  _validate_patch_paths()
    @calls: ToolResult, source_filename.startswith, target_filename.startswith
    @returns: BinOp

  _get_source_read_path()
    @calls: get_safe_path, len, os.path.dirname, os.path.join, source_filename.startswith
    @returns: str

  _handle_create_file()
    @calls: get_safe_path, params.get, tpool.execute
    @returns: ToolResult

  _handle_read_file()
    @calls: ToolResult, get_safe_path, params.get, tpool.execute
    @returns: ToolResult

  _handle_read_project_file()
    @calls: ToolResult, os.path.dirname, os.path.join, params.get, tpool.execute
    @returns: ToolResult

  _handle_list_allowed_project_files()
    @calls: ToolResult
    @returns: ToolResult

  _handle_list_directory()
    @calls: get_safe_path, tpool.execute
    @returns: ToolResult

  _handle_delete_file()
    @calls: ToolResult, get_safe_path, params.get, tpool.execute
    @returns: ToolResult

  _handle_execute_python_script()
    @calls: params.get, tpool.execute
    @returns: ToolResult

  _handle_apply_patch()
    @calls: ToolResult, _extract_patch_paths, _get_source_read_path, _validate_patch_paths, diff_content.replace, get_safe_path, len, os.path.exists, params.get, patcher.apply_patch, tpool.execute
    @returns: ToolResult

  _handle_list_sessions()
    @calls: ToolResult, chroma_client.list_collections, chromadb.PersistentClient, col.name.startswith, context.haven_proxy.list_sessions, db_sessions.items, name.replace, session_list.sort
    @creates: list
    @returns: ToolResult

  _handle_load_session()
    @calls: ActiveSession, ChromaDBStore, HavenProxyWrapper, MemoryManager, ToolResult, context.haven_proxy.get_or_create_session, context.socketio.emit, params.get, replay_history_for_client, turn_store.get_all_records
    @creates: ActiveSession, HavenProxyWrapper, MemoryManager
    @returns: ToolResult

  _handle_save_session()
    @calls: ChromaDBStore, HavenProxyWrapper, ToolResult, context.chat_sessions.get, context.haven_proxy.get_or_create_session, context.socketio.emit, params.get, source_code_store.get_all_records, source_turn_store.get_all_records, str, target_code_store.add_record, target_turn_store.add_record
    @creates: HavenProxyWrapper, str
    @returns: ToolResult

  _handle_delete_session()
    @calls: ChromaDBStore, ToolResult, _handle_list_sessions, code_store.delete_collection, context.haven_proxy.delete_session, context.socketio.emit, logging.error, params.get, turn_store.delete_collection, updated_list_result.model_dump
    @creates: list
    @returns: ToolResult

  execute_tool_command()
    @calls: TOOL_REGISTRY.get, ToolContext, ToolResult, handler, logging.error
    @returns: ToolResult

Classes:
  ToolContext


## Cross-Module Interactions
