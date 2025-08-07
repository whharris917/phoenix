# Sequence Diagram for: 03_complex_prompt_with_tools (Haven Service)

**Description**: Traces a complex prompt that requires the agent to use tools (in this case, listing files).

```mermaid
sequenceDiagram
    autonumber
    actor Client
    participant haven

    Client->>+haven: configure_logging()
    haven-->>-Client: return_value
    Client->>+haven: initialize_model()
    haven->>+haven: load_model_definition()
    haven-->>-haven: return_value
    haven->>+haven: load_system_prompt()
    haven-->>-haven: return_value
    haven-->>-Client: return_value
    Client->>+haven: start_haven()
    haven->>+haven: Haven.get_or_create_session()
    haven-->>-haven: return_value
    haven->>+haven: Haven.send_message()
    haven-->>-haven: return_value
    haven->>+haven: Haven.send_message()
    haven->>+haven: Haven.get_trace_log()
    haven-->>-haven: return_value
    haven-->>-haven: return_value
    haven-->>-Client: return_value
```