# System Interaction Map

This diagram illustrates the primary interactions and call flows between the major components of the Phoenix Agent system. It is generated automatically from the source code.

```mermaid
graph TD

    classDef SocketIOClient fill:#f9f,stroke:#333,stroke-width:2px
    classDef ToolAgent fill:#f9f,stroke:#333,stroke-width:2px
    classDef Orchestrator fill:#f9f,stroke:#333,stroke-width:2px
    classDef MemoryManager fill:#f9f,stroke:#333,stroke-width:2px
    classDef ResponseParser fill:#f9f,stroke:#333,stroke-width:2px
    classDef HavenProxy fill:#f9f,stroke:#333,stroke-width:2px
    classDef WebApp fill:#f9f,stroke:#333,stroke-width:2px
    classDef Haven fill:#f9f,stroke:#333,stroke-width:2px
    HavenProxy[Haven Proxy] -->|send_message| Haven[Haven]
    Orchestrator[Orchestrator] -->|add_turn| MemoryManager[Memory Manager]
    Orchestrator[Orchestrator] -->|prepare_augmented_prompt| MemoryManager[Memory Manager]
    Orchestrator[Orchestrator] -->|parse_agent_response| ResponseParser[Response Parser]
    Orchestrator[Orchestrator] -->|emit| SocketIOClient[SocketIO Client]
    Orchestrator[Orchestrator] -->|execute_tool_command| ToolAgent[Tool Agent]
    ToolAgent[Tool Agent] -->|delete_session| Haven[Haven]
    ToolAgent[Tool Agent] -->|get_or_create_session| Haven[Haven]
    ToolAgent[Tool Agent] -->|emit| SocketIOClient[SocketIO Client]

    class SocketIOClient SocketIOClient
    class ToolAgent ToolAgent
    class Orchestrator Orchestrator
    class MemoryManager MemoryManager
    class ResponseParser ResponseParser
    class HavenProxy HavenProxy
    class WebApp WebApp
    class Haven Haven
```
