from multiprocessing.managers import BaseManager
import logging
import os
import vertexai
from vertexai.generative_models import (
    GenerativeModel,
    HarmCategory,
    HarmBlockThreshold,
    Content,
    Part,
)

# --- Setup Logging ---
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - Haven - %(levelname)s - %(message)s"
)


# --- Function to load the system prompt from a file ---
def load_system_prompt():
    try:
        prompt_path = os.path.join(
            os.path.dirname(__file__), "public_data", "system_prompt.txt"
        )
        with open(prompt_path, "r") as f:
            return f.read()
    except FileNotFoundError:
        return "You are a helpful assistant but were unable to locate or open system_prompt.txt, and thus do not have access to your core directives."


# --- Function to load the model definition from a file ---
def load_model_definition():
    try:
        model_definition_path = os.path.join(
            os.path.dirname(__file__), "public_data", "model_definition.txt"
        )
        with open(model_definition_path, "r") as f:
            return f.read().strip()
    except FileNotFoundError:
        return "gemini-1.5-pro-001"


# --- CONFIGURATION & MODEL SETUP (MOVED FROM APP.PY) ---
PROJECT_ID = "long-ratio-463815-n7"
LOCATION = "us-east1"
SYSTEM_PROMPT = load_system_prompt()
MODEL_DEFINITION = load_model_definition()
model = None

try:
    vertexai.init(project=PROJECT_ID, location=LOCATION)
    safety_settings = {
        HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
        HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
        HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
        HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
    }
    model = GenerativeModel(
        model_name=MODEL_DEFINITION,
        system_instruction=[SYSTEM_PROMPT],
        safety_settings=safety_settings,
    )
    logging.info(
        f"Haven: Vertex AI configured successfully for project '{PROJECT_ID}' and model '{MODEL_DEFINITION}'."
    )
except Exception as e:
    logging.critical(f"Haven: FATAL: Failed to configure Vertex AI. Error: {e}")
    # We should exit if the model fails to load, as the Haven is useless without it.
    exit(1)

# This is the single, persistent object that will survive app reboots.
# The keys will be session_names, and the values will be the live chat objects.
live_chat_sessions = {}


class Haven:
    """
    The Haven class manages the live GenerativeModel chat objects.
    An instance of this class will be served by the BaseManager.
    """

    def get_or_create_session(self, session_name, history_dicts):
        """
        Gets a session if it exists, otherwise creates a new one by
        storing the history list directly.
        """
        if session_name not in live_chat_sessions:
            logging.info(
                f"Haven: Creating new history list for session: '{session_name}'"
            )
            # Convert the raw dictionaries to a list of Content objects
            history_content = [
                Content(
                    role=turn.get("role"),
                    parts=[
                        Part.from_text(
                            (turn.get("parts", [{}])[0] or {}).get("text", "")
                        )
                    ],
                )
                for turn in history_dicts
            ]
            # Store the list directly, INSTEAD of a chat object
            live_chat_sessions[session_name] = history_content
        else:
            logging.info(
                f"Haven: Reconnecting to existing history list for session: '{session_name}'"
            )
        return True

    def send_message(self, session_name, prompt):
        """
        Sends a message by appending to the history and making a stateless
        call to model.generate_content().
        """
        if session_name not in live_chat_sessions:
            logging.error(
                f"Haven: Attempted to send message to non-existent session: '{session_name}'"
            )
            return {"status": "error", "message": "Session history not found in Haven."}

        try:
            # 1. Retrieve the current history list
            history = live_chat_sessions[session_name]

            # 2. Append the new user prompt to the history
            history.append(Content(role="user", parts=[Part.from_text(prompt)]))

            # 3. Make the stateless API call with the entire history
            response = model.generate_content(history)

            # 4. Append the model's response to the history to keep it current
            history.append(response.candidates[0].content)

            # 5. Return the response text
            return {"status": "success", "text": response.text}
        except Exception as e:
            logging.error(
                f"Haven: Error during generate_content for session '{session_name}': {e}"
            )
            return {"status": "error", "message": str(e)}

    def list_sessions(self):
        """Returns a list of the names of the live sessions."""
        return list(live_chat_sessions.keys())

    def delete_session(self, session_name):
        """NEW: Deletes a session from the live dictionary to prevent memory leaks."""
        if session_name in live_chat_sessions:
            del live_chat_sessions[session_name]
            logging.info(f"Haven: Deleted live session '{session_name}'.")
            return {
                "status": "success",
                "message": f"Live session '{session_name}' deleted.",
            }
        else:
            logging.warning(
                f"Haven: Attempted to delete non-existent live session '{session_name}'."
            )
            return {"status": "success", "message": "Session was not live in Haven."}

    def has_session(self, session_name):
        """Checks if a session exists in the Haven."""
        return session_name in live_chat_sessions


# --- Manager Setup ---
class HavenManager(BaseManager):
    pass


def start_haven():
    """Starts the Haven server process."""
    # Create an instance of our Haven class
    haven_instance = Haven()

    # Register the Haven class itself with the manager.
    # We can now access any method of the Haven instance remotely.
    HavenManager.register("get_haven", lambda: haven_instance)
    manager = HavenManager(address=("", 50000), authkey=b"phoenixhaven")

    logging.info(
        "Haven server started. Serving the persistent Haven object on port 50000."
    )

    server = manager.get_server()
    server.serve_forever()


if __name__ == "__main__":
    logging.info("Initializing Haven...")
    start_haven()
