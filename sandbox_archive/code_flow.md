graph TD

    subgraph app
        load_system_prompt
        load_model_definition
        serve_index
        serve_audit_visualizer
        serve_database_viewer
        serve_docs
        serve_markdown
        serve_workshop
        serve_visualizer
        get_diagram_file
        handle_connect
        handle_disconnect
        handle_start_task
        handle_audit_event
        handle_session_list_request
        handle_session_name_request
        handle_db_collections_request
        handle_db_collection_data_request
        handle_user_confirmation
    end

    subgraph orchestrator
        _log_turn_to_file
        _mask_payloads
        parse_agent_response
        _extract_json_with_fences
        _extract_json_with_brace_counting
        _repair_json
        _clean_prose
        _handle_payloads
        _emit_agent_message
        _render_user_turn
        _process_and_render_model_turn
        replay_history_for_client
        execute_reasoning_loop
        is_prose_effectively_empty
    end

    subgraph tool_agent
        _execute_script
        _write_file
        _read_file
        _delete_file
        _list_directory
        get_safe_path
        execute_tool_command
    end

    get_diagram_file --> get_safe_path
    handle_session_list_request --> execute_tool_command
    parse_agent_response --> _mask_payloads
    parse_agent_response --> _extract_json_with_fences
    parse_agent_response --> _extract_json_with_brace_counting
    parse_agent_response --> _repair_json
    parse_agent_response --> is_prose_effectively_empty
    parse_agent_response --> _clean_prose
    parse_agent_response --> is_prose_effectively_empty
    parse_agent_response --> _clean_prose
    parse_agent_response --> is_prose_effectively_empty
    parse_agent_response --> _clean_prose
    _extract_json_with_brace_counting --> _repair_json
    _process_and_render_model_turn --> parse_agent_response
    _process_and_render_model_turn --> _handle_payloads
    _process_and_render_model_turn --> _emit_agent_message
    _process_and_render_model_turn --> _emit_agent_message
    _process_and_render_model_turn --> _emit_agent_message
    _process_and_render_model_turn --> _emit_agent_message
    replay_history_for_client --> parse_agent_response
    replay_history_for_client --> _handle_payloads
    execute_reasoning_loop --> _process_and_render_model_turn
    execute_reasoning_loop --> execute_tool_command
    execute_tool_command --> get_safe_path
    execute_tool_command --> get_safe_path
    execute_tool_command --> get_safe_path
    execute_tool_command --> get_safe_path
    execute_tool_command --> get_safe_path
    execute_tool_command --> get_safe_path
    execute_tool_command --> get_safe_path
    execute_tool_command --> get_safe_path
    execute_tool_command --> replay_history_for_client
    execute_tool_command --> execute_tool_command
    execute_tool_command --> execute_tool_command
