# Introduction

This document provides a high-level overview of the Gemini Local Agent project. The system is designed to allow a user to interact with their local file system through a natural language interface, powered by Google's Gemini model. The architecture is split into distinct logical components within a single, unified server application to ensure security, modularity, and a responsive user experience.

---

## System Architecture

The project follows a multi-tier architecture consolidated into a single server application for ease of use and deployment. The logical tiers are:

1.  **Front-End (UI)**: A web-based interface where the user interacts with the system.
2.  **Orchestrator (Reasoning Engine)**: The part of the server that communicates with the Gemini API to manage the conversation and reasoning process.
3.  **Tool Agent (Executor)**: The part of the server that has direct, but sandboxed, access to the local file system to execute specific, safe commands.

---

## Component Breakdown

### 1. User Interface (`index.html`)
This is the user's window into the system. It's a single HTML file served by our main application.

-   **Responsibility**: To capture user prompts and display the real-time flow of the conversation, agent thoughts, and final results.
-   **Communication**: It communicates with the Orchestrator logic on the main server via a persistent **WebSocket** connection.

### 2. Unified Server (`app.py`)
This is the single, unified backend for the entire application. It runs in one terminal and handles all logic.

-   **Orchestrator Logic**:
    -   **Responsibility**: Manages the reasoning loop. It receives a high-level command from the user (via WebSocket), communicates with the **Google Gemini API** to break it down into executable steps, and calls the internal Tool Agent logic.
    -   **Communication**: Listens for prompts from the UI on a WebSocket channel and sends API calls to the external Google Gemini API.

-   **Tool Agent Logic**:
    -   **Responsibility**: To execute a predefined set of safe, low-level commands (e.g., `create_file`, `read_file`). It contains critical security checks to ensure all operations are confined to the `/sandbox` directory.
    -   **Communication**: Listens for JSON commands from the Orchestrator logic via an internal function call at the `/execute` HTTP endpoint.

-   **Web Server Logic**:
    -   **Responsibility**: Serves all static files to the user, including `index.html` and the documentation pages.

---

## Workflow: A Step-by-Step Example

Consider the user prompt: *What vegetable is in the story file?*

1.  **User Input**: The user types the prompt into the `index.html` interface.
2.  **UI to Orchestrator**: The UI sends the prompt via WebSocket to the `app.py` server.
3.  **Orchestrator to Gemini**: The Orchestrator logic within `app.py` sends the prompt to the Gemini API, asking for the first step. Gemini responds with a JSON command: `{"action": "list_directory", "parameters": {}}`.
4.  **Orchestrator to Tool Agent**: The Orchestrator logic calls the internal Tool Agent logic by making a request to its own `/execute` endpoint.
5.  **Tool Agent Execution**: The Tool Agent logic executes the command, lists the files in the `/sandbox` folder, and returns the result.
6.  **Reasoning Loop**: The Orchestrator receives the file list and sends it back to the Gemini API as context. Gemini now knows the filename and responds with the next command: `{"action": "read_file", "parameters": {"filename": "story.txt"}}`.
7.  **Final Execution**: This command is executed by the Tool Agent logic, which returns the file's content.
8.  **Final Answer**: The Orchestrator sends the content to Gemini. Gemini formulates the final answer ("The vegetable mentioned was a carrot."), which is sent back to the UI via WebSocket.