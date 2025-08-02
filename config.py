import os

PROJECT_ID = "long-ratio-463815-n7"
LOCATION = "us-east1"
CHROMA_DB_PATH = os.path.join(os.path.dirname(__file__), ".sandbox", "chroma_db")
SUMMARIZER_MODEL_NAME = "gemini-2.0-flash-lite-001"
SEGMENT_THRESHOLD = 20
ABSOLUTE_MAX_ITERATIONS_REASONING_LOOP = 10
NOMINAL_MAX_ITERATIONS_REASONING_LOOP = 3

ALLOWED_PROJECT_FILES = [
    "public_data/system_prompt.txt",
    "app.py",
    "audit_logger.py",
    "audit_visualizer.py",
    "code_parser.py",
    "code_visualizer.py",
    "config.py",
    "database_viewer.html",
    "documentation_viewer.html",
    "haven.py",
    "index.html",
    "inspect_db.py",
    "memory_manager.py",
    "orchestrator.py",
    "patcher.py",
    "requirements.txt",
    "tool_agent.py",
    "workshop.html",
]
