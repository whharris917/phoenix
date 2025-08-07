"""
The Haven: A persistent, stateful service for managing AI model chat sessions.

This script runs as a separate, dedicated process. Its sole purpose is to hold the
expensive GenerativeModel object and all live chat histories in memory, safe
from the restarts and stateless nature of the main web application.

The core state is managed in the module-level 'live_chat_sessions' dictionary.
The main app connects to this service to send prompts and receive responses.
"""
from multiprocessing.managers import BaseManager
import logging
import os
from typing import Any, List, Optional
import vertexai
from vertexai.generative_models import GenerativeModel, Content, Part
from config import PROJECT_ID, LOCATION, SAFETY_SETTINGS
from tracer import trace, global_tracer

@trace
def configure_logging() -> None:
    """
    Configures the global logging settings for the Haven service.
    """
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - Haven - %(levelname)s - %(message)s")

@trace
def load_system_prompt() -> str:
    """Loads the system prompt text from the 'system_prompt.txt' file."""
    try:
        prompt_path = os.path.join(os.path.dirname(__file__), "public_data", "system_prompt.txt")
        with open(prompt_path, "r") as f:
            return f.read()
    except FileNotFoundError:
        return "You are a helpful assistant but were unable to locate or open system_prompt.txt, and thus do not have access to your core directives."

@trace
def load_model_definition() -> str:
    """Loads the model name from the 'model_definition.txt' file."""
    try:
        model_definition_path = os.path.join(os.path.dirname(__file__), "public_data", "model_definition.txt")
        with open(model_definition_path, "r") as f:
            return f.read().strip()
    except FileNotFoundError:
        return "gemini-1.5-pro-001"

@trace
def initialize_model() -> Optional[GenerativeModel]:
    """
    Initializes the connection to Vertex AI and loads the generative model.

    This is a critical, one-time setup step for the Haven service.

    Returns:
        The initialized GenerativeModel object on success, otherwise None.
    """
    try:
        vertexai.init(project=PROJECT_ID, location=LOCATION)
        model = GenerativeModel(
            model_name=load_model_definition(),
            system_instruction=[load_system_prompt()],
            safety_settings=SAFETY_SETTINGS,
        )
        logging.info(f"Haven: Vertex AI configured successfully for project '{PROJECT_ID}'.")
        return model
    except Exception as e:
        logging.critical(f"Haven: FATAL: Failed to configure Vertex AI. Error: {e}")
        return None

# --- Bootstrap Sequence ---
configure_logging()
model = initialize_model()

# This dictionary is the core state managed by Haven. It holds the complete,
# ordered list of Content objects (user and model turns) for each session.
live_chat_sessions: dict[str, list[Content]] = {}


class Haven:
    """
    The Haven class manages the live GenerativeModel chat histories.
    An instance of this class is served by the BaseManager to act as a
    persistent, stateful service for the main application.
    """
    @trace
    def get_or_create_session(self, session_name: str, history_dicts: list[dict]) -> bool:
        """
        Gets a session history if it exists, otherwise creates a new one.

        This ensures that if the main app restarts, it can reconnect to the
        histories that have been preserved in this Haven process.

        Args:
            session_name: The unique identifier for the session.
            history_dicts: A list of dictionaries representing conversation turns,
                           used to hydrate a new session's history if it's the first time
                           it's being loaded in this Haven instance.

        Returns:
            True, indicating the session history is ready.
        """
        if session_name not in live_chat_sessions:
            logging.info(f"Haven: Creating new history list for session: '{session_name}'.")
            # Convert the raw dictionaries from the client/DB into Vertex AI Content objects.
            history_content = [
                Content(
                    role=turn.get("role"),
                    parts=[Part.from_text((turn.get("parts", [{}])[0] or {}).get("text", ""))],
                )
                for turn in history_dicts
            ]
            live_chat_sessions[session_name] = history_content
        else:
            logging.info(f"Haven: Reconnecting to existing history list for session: '{session_name}'.")
        return True

    @trace
    def send_message(self, session_name: str, prompt: str) -> dict[str, Any]:
        """
        Sends a message by appending to the history and making a stateless
        call to model.generate_content().

        Args:
            session_name: The session to send the message to.
            prompt: The user's prompt text.

        Returns:
            A dictionary with 'status' and either 'text' on success or 'message' on error.
        """
        if session_name not in live_chat_sessions:
            logging.error(f"Haven: Attempted to send message to non-existent session: '{session_name}'.")
            return {"status": "error", "message": "Session history not found in Haven."}

        try:
            # 1. Retrieve the current history list for the session.
            history = live_chat_sessions[session_name]

            # 2. Append the new user prompt to the end of the history.
            history.append(Content(role="user", parts=[Part.from_text(prompt)]))

            # 3. Make the stateless API call with the entire, updated history.
            response = model.generate_content(history)

            # 4. Append the model's response to the history to keep it current for the next turn.
            history.append(response.candidates[0].content)

            # 5. Return only the new response text to the caller.
            return {"status": "success", "text": response.text}
        except Exception as e:
            logging.error(f"Haven: Error during generate_content for session '{session_name}': {e}.")
            return {"status": "error", "message": str(e)}

    @trace
    def list_sessions(self) -> list[str]:
        """Returns a list of the names of all currently live sessions."""
        return list(live_chat_sessions.keys())

    @trace
    def delete_session(self, session_name: str) -> dict[str, str]:
        """Deletes a session from the live dictionary to free up memory."""
        if session_name in live_chat_sessions:
            del live_chat_sessions[session_name]
            logging.info(f"Haven: Deleted live session '{session_name}'.")
            return {"status": "success", "message": f"Live session '{session_name}' deleted."}
        else:
            logging.warning(f"Haven: Attempted to delete non-existent live session '{session_name}'.")
            return {"status": "success", "message": "Session was not live in Haven."}

    @trace
    def has_session(self, session_name: str) -> bool:
        """Checks if a session exists in the Haven."""
        return session_name in live_chat_sessions

    @trace
    def get_trace_log(self):
        """Returns the trace log from this Haven process."""
        return global_tracer.get_trace()


# --- Manager Setup ---
class HavenManager(BaseManager):
    """A multiprocessing manager for serving the Haven instance."""
    pass

@trace
def start_haven() -> None:
    """Initializes and starts the Haven server process."""
    haven_instance = Haven()
    # Register the Haven class with the manager, allowing remote access.
    HavenManager.register("get_haven", lambda: haven_instance)
    manager = HavenManager(address=("", 50000), authkey=b"phoenixhaven")
    logging.info("Haven server started. Serving the persistent Haven object on port 50000.")
    server = manager.get_server()
    # This starts the server loop, making it wait for connections indefinitely.
    server.serve_forever()

if __name__ == "__main__":
    if not model:
        logging.critical("Haven startup failed: GenerativeModel could not be initialized.")
    else:
        logging.info("Initializing Haven...")
        start_haven()
