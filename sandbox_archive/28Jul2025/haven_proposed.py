import os
import logging
import google.generativeai as genai
from multiprocessing.managers import BaseManager
from memory_manager import MemoryManager

# --- Logging Setup ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - Haven - %(levelname)s - %(message)s')

# --- Helper Functions (Copied from app.py for self-containment) ---
def load_api_key():
    try:
        key_path = os.path.join(os.path.dirname(__file__), 'private_data', 'Gemini_API_Key.txt')
        with open(key_path, 'r') as f:
            return f.read().strip()
    except FileNotFoundError:
        return None

def load_system_prompt():
    try:
        prompt_path = os.path.join(os.path.dirname(__file__), 'public_data', 'system_prompt.txt')
        with open(prompt_path, 'r') as f:
            return f.read()
    except FileNotFoundError:
        return "System prompt file not found."

# --- The Core Haven Class ---
class Haven:
    def __init__(self):
        logging.info("Initializing Haven instance...")
        self._sessions = {}
        
        # Initialize the Gemini Model right inside the Haven
        api_key = load_api_key()
        if not api_key:
            logging.critical("FATAL: Gemini API key not found. Haven cannot start.")
            raise ValueError("API Key not found")
            
        genai.configure(api_key=api_key)
        safety_settings = {
            'HARM_CATEGORY_HARASSMENT': 'BLOCK_NONE',
            'HARM_CATEGORY_HATE_SPEECH': 'BLOCK_NONE',
            'HARM_CATEGORY_SEXUALLY_EXPLICIT': 'BLOCK_NONE',
            'HARM_CATEGORY_DANGEROUS_CONTENT': 'BLOCK_NONE',
        }
        self._model = genai.GenerativeModel(
            model_name='gemini-1.5-pro-latest',
            system_instruction=load_system_prompt(),
            safety_settings=safety_settings
        )
        logging.info("Gemini Model initialized successfully within Haven.")

    def get_or_create_session(self, session_name):
        """
        Retrieves an existing session or creates a new one.
        This is the primary way the app will get a chat session.
        """
        if session_name not in self._sessions:
            logging.info(f"Creating new session: {session_name}")
            memory = MemoryManager(session_name=session_name)
            chat = self._model.start_chat(history=memory.get_full_history())
            self._sessions[session_name] = {'memory': memory, 'chat': chat}
        else:
            logging.info(f"Re-attaching to existing session: {session_name}")
        return True # Return simple success confirmation

    def send_message(self, session_name, prompt):
        """
        Handles sending a message to a specific chat session and records the turn.
        """
        if session_name not in self._sessions:
            return {"status": "error", "message": "Session not found in Haven."}
        
        session = self._sessions[session_name]
        chat = session['chat']
        memory = session['memory']

        try:
            memory.add_turn("user", prompt)
            response = chat.send_message(prompt)
            memory.add_turn("model", response.text)
            return {"status": "success", "text": response.text}
        except Exception as e:
            logging.error(f"Error in send_message for session '{session_name}': {e}")
            return {"status": "error", "message": str(e)}

    def get_full_history(self, session_name):
        if session_name not in self._sessions:
            return []
        return self._sessions[session_name]['memory'].get_full_history()

    def list_sessions(self):
        """Lists the names of all active sessions in the Haven."""
        return list(self._sessions.keys())

    def rename_session(self, old_name, new_name):
        if old_name in self._sessions:
            logging.info(f"Renaming session '{old_name}' to '{new_name}'")
            session_data = self._sessions.pop(old_name)
            session_data['memory'].rename_collection(new_name)
            self._sessions[new_name] = session_data
            return True
        return False

    def delete_session(self, session_name):
        if session_name in self._sessions:
            logging.info(f"Deleting session '{session_name}' from Haven.")
            session_data = self._sessions.pop(session_name)
            session_data['memory'].clear() # Deletes the underlying ChromaDB collection
            return True
        return False

# --- Manager Setup ---
class HavenManager(BaseManager):
    pass

def start_haven_server():
    """Initializes and serves the Haven instance."""
    haven_instance = Haven()
    
    HavenManager.register('get_haven', lambda: haven_instance)
    
    manager = HavenManager(address=('', 50000), authkey=b'phoenixhaven')
    
    logging.info("Haven server starting... Ready to accept connections.")
    server = manager.get_server()
    server.serve_forever()

if __name__ == '__main__':
    start_haven_server()