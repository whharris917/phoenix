# Hierarchical Call Trees

Generated from static analysis. Found 14 potential entry points.

## events._create_new_session
```
events._create_new_session
├── ActiveSession [EXTERNAL]
├── HavenProxyWrapper [EXTERNAL]
├── MemoryManager [EXTERNAL]
├── get_timestamp [EXTERNAL]
├── logging.info [EXTERNAL]
└── proxy.get_or_create_session [EXTERNAL]
```

## events.handle_audit_log
```
events.handle_audit_log
├── audit_log.log_event [EXTERNAL]
├── chat_sessions.get [EXTERNAL]
├── data.get [EXTERNAL]
└── socketio.on [EXTERNAL]
```

## events.handle_connect
```
events.handle_connect
├── _create_new_session [EXTERNAL]
├── auth.get [EXTERNAL]
├── logging.exception [EXTERNAL]
├── logging.info [EXTERNAL]
├── socketio.emit [EXTERNAL]
└── socketio.on [EXTERNAL]
```

## events.handle_db_collection_data_request
```
events.handle_db_collection_data_request
├── data.get [EXTERNAL]
├── db_inspector.get_collection_data_as_json [EXTERNAL]
├── socketio.emit [EXTERNAL]
└── socketio.on [EXTERNAL]
```

## events.handle_db_collections_request
```
events.handle_db_collections_request
├── db_inspector.list_collections_as_json [EXTERNAL]
├── socketio.emit [EXTERNAL]
└── socketio.on [EXTERNAL]
```

## events.handle_disconnect
```
events.handle_disconnect
├── chat_sessions.pop [EXTERNAL]
├── confirmation_events.pop [EXTERNAL]
├── logging.info [EXTERNAL]
└── socketio.on [EXTERNAL]
```

## events.handle_get_haven_trace_log
```
events.handle_get_haven_trace_log
├── _haven_proxy.get_trace_log [EXTERNAL]
├── logging.info [EXTERNAL]
├── socketio.emit [EXTERNAL]
└── socketio.on [EXTERNAL]
```

## events.handle_get_trace_log
```
events.handle_get_trace_log
├── global_tracer.get_trace [EXTERNAL]
├── logging.info [EXTERNAL]
├── socketio.emit [EXTERNAL]
└── socketio.on [EXTERNAL]
```

## events.handle_session_list_request
```
events.handle_session_list_request
├── ToolCommand [EXTERNAL]
├── execute_tool_command [EXTERNAL]
├── socketio.emit [EXTERNAL]
├── socketio.on [EXTERNAL]
└── tool_result.model_dump [EXTERNAL]
```

## events.handle_session_name_request
```
events.handle_session_name_request
├── chat_sessions.get [EXTERNAL]
├── socketio.emit [EXTERNAL]
└── socketio.on [EXTERNAL]
```

## events.handle_start_task
```
events.handle_start_task
├── chat_sessions.get [EXTERNAL]
├── data.get [EXTERNAL]
├── get_timestamp [EXTERNAL]
├── socketio.emit [EXTERNAL]
├── socketio.on [EXTERNAL]
└── socketio.start_background_task [EXTERNAL]
```

## events.handle_user_confirmation
```
events.handle_user_confirmation
├── confirmation_events.get [EXTERNAL]
├── data.get [EXTERNAL]
├── event.send [EXTERNAL]
└── socketio.on [EXTERNAL]
```

## events.register_events
```
events.register_events
```

## events.replay_history_for_client
```
events.replay_history_for_client
├── BoolOp.get [EXTERNAL]
├── ToolResult.model_validate [EXTERNAL]
├── _handle_payloads [EXTERNAL]
├── isinstance [EXTERNAL]
├── item.get [EXTERNAL]
├── json.loads [EXTERNAL]
├── len [EXTERNAL]
├── logging.error [EXTERNAL]
├── parse_agent_response [EXTERNAL]
├── parsed.command.parameters.get [EXTERNAL]
├── raw_text.find [EXTERNAL]
├── raw_text.startswith [EXTERNAL]
├── raw_text.strip [EXTERNAL]
├── socketio.emit [EXTERNAL]
└── socketio.sleep [EXTERNAL]
```
