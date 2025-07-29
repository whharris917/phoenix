graph TD

    subgraph app
        load_api_key
        load_system_prompt
        load_model_definition
        load_api_stats
        save_api_stats
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
        handle_api_stats_request
        handle_session_name_request
        handle_db_collections_request
        handle_db_collection_data_request
        handle_user_confirmation
    end

    subgraph orchestrator
        parse_agent_response
        _extract_json_with_fences
        _extract_json_with_brace_counting
        _repair_json
        _clean_prose
        _handle_payloads
        replay_history_for_client
        execute_reasoning_loop
        get_current_session_name
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
    parse_agent_response --> _extract_json_with_fences
    parse_agent_response --> _clean_prose
    parse_agent_response --> _repair_json
    parse_agent_response --> _clean_prose
    parse_agent_response --> _extract_json_with_brace_counting
    parse_agent_response --> _clean_prose
    parse_agent_response --> _repair_json
    parse_agent_response --> _clean_prose
    parse_agent_response --> _clean_prose
    parse_agent_response --> _clean_prose
    _extract_json_with_brace_counting --> _repair_json
    replay_history_for_client --> parse_agent_response
    execute_reasoning_loop --> get_current_session_name
    execute_reasoning_loop --> get_current_session_name
    execute_reasoning_loop --> get_current_session_name
    execute_reasoning_loop --> get_current_session_name
    execute_reasoning_loop --> get_current_session_name
    execute_reasoning_loop --> get_current_session_name
    execute_reasoning_loop --> get_current_session_name
    execute_reasoning_loop --> get_current_session_name
    execute_reasoning_loop --> get_current_session_name
    execute_reasoning_loop --> parse_agent_response
    execute_reasoning_loop --> get_current_session_name
    execute_reasoning_loop --> _handle_payloads
    execute_reasoning_loop --> get_current_session_name
    execute_reasoning_loop --> get_current_session_name
    execute_reasoning_loop --> get_current_session_name
    execute_reasoning_loop --> get_current_session_name
    execute_reasoning_loop --> get_current_session_name
    execute_reasoning_loop --> get_current_session_name
    execute_reasoning_loop --> execute_tool_command
    execute_reasoning_loop --> get_current_session_name
    execute_reasoning_loop --> get_current_session_name
    execute_reasoning_loop --> get_current_session_name
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
