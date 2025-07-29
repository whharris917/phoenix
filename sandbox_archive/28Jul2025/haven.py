from multiprocessing.managers import BaseManager
import logging

# --- Setup Logging ---
logging.basicConfig(
    level=logging.INFO, 
    format='%(asctime)s - Haven - %(levelname)s - %(message)s'
)

# This is the single, persistent object that will survive app reboots.
# The keys will be session_names, and the values will be the live chat objects.
chat_sessions = {}

class HavenManager(BaseManager):
    pass

def start_haven():
    """Starts the Haven server process."""
    HavenManager.register('get_sessions', lambda: chat_sessions)
    
    # Use a secret authkey for security
    manager = HavenManager(address=('', 50000), authkey=b'phoenixhaven')
    
    logging.info("Haven server started. Serving the persistent session dictionary on port 50000.")
    
    server = manager.get_server()
    server.serve_forever()

if __name__ == '__main__':
    logging.info("Initializing Haven...")
    start_haven()