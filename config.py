import os
from vertexai.generative_models import HarmCategory, HarmBlockThreshold

PROJECT_ID = "long-ratio-463815-n7"
LOCATION = "us-east1"
SUMMARIZER_MODEL_NAME = "gemini-2.0-flash-lite-001"
SEGMENT_THRESHOLD = 20
ABSOLUTE_MAX_ITERATIONS_REASONING_LOOP = 10
NOMINAL_MAX_ITERATIONS_REASONING_LOOP = 3

ALLOWED_PROJECT_FILES = [
    "public_data/system_prompt.txt",
    "phoenix.py",
    "audit_logger.py",
    "audit_visualizer.html",
    "config.py",
    "data_models.py",
    "database_viewer.html",
    "documentation_viewer.html",
    "events.py",
    "generate_code_map.py",
    "haven.py",
    "index.html",
    "inspect_db.py",
    "main.js",
    "memory_manager.py",
    "orchestrator.py",
    "patcher.py",
    "proxies.py",
    "requirements.txt",
    "session_models.py",
    "summarizer.py",
    "tool_agent.py",
    "utils.py",
    "workshop.html",
]


DEBUG_MODE = False

SAFETY_SETTINGS = {
    HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
    HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
    HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
    HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
}

# Ensure the ChromaDB directory exists
# os.makedirs(CHROMA_DB_PATH, exist_ok=True)
CHROMA_DB_PATH = os.path.join(os.path.dirname(__file__), ".sandbox", "chroma_db")

# Server configuration
SERVER_PORT = 5001

# Haven service connection details
HAVEN_ADDRESS = ("localhost", 50000)
HAVEN_AUTH_KEY = b"phoenixhaven"
