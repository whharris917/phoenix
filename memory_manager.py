import chromadb
import logging
import uuid
import os
import chromadb.utils.embedding_functions as embedding_functions

# This script will be in the project root. The sandbox is a subdirectory.
SANDBOX_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.sandbox')
CHROMA_DB_PATH = os.path.join(SANDBOX_DIR, 'chroma_db')

# Ensure the ChromaDB directory exists
os.makedirs(CHROMA_DB_PATH, exist_ok=True)
logging.info(f"ChromaDB path set to: {CHROMA_DB_PATH}")


# --- NEW: Explicitly define the embedding function ---
# This forces ChromaDB to use a known, pre-loaded model, preventing silent failures
# during the automatic download of the default model.
try:
    # Use the default embedding function which relies on sentence-transformers.
    # This will download the model 'all-MiniLM-L6-v2' on its first run if not cached.
    # By instantiating it here, we ensure any download/load errors happen at startup, not silently later.
    embedding_function = embedding_functions.DefaultEmbeddingFunction()
    logging.info("Successfully initialized the default sentence-transformer embedding model.")
except Exception as e:
    logging.critical(f"FATAL: Failed to initialize the embedding model: {e}")
    logging.critical("This is likely a network issue or a problem with the sentence-transformers installation.")
    # Set to None so the application can handle the failure gracefully.
    embedding_function = None


class MemoryManager:
    """
    Manages the Tiered Memory Architecture for the AI agent.

    Tier 1: Conversational Buffer (Short-Term Memory)
    Tier 3: Vector Store (Long-Term, Specific Recall)
    """
    def __init__(self, session_id):
        self.session_id = session_id
        self.max_buffer_size = 12 # Number of conversational turns

        # Tier 1: Conversational Buffer
        self.conversational_buffer = []

        # Tier 3: Vector Store (ChromaDB)
        if embedding_function is None:
            logging.error(f"Cannot initialize ChromaDB for session {self.session_id} because embedding function failed to load.")
            self.collection = None
            return

        try:
            self.chroma_client = chromadb.PersistentClient(path=CHROMA_DB_PATH)
            
            # Sanitize session_id for collection name
            collection_name = f"session_{self.session_id.replace('-', '_').replace('.', '_')}"
            
            # --- MODIFIED: Pass the explicit embedding function ---
            self.collection = self.chroma_client.get_or_create_collection(
                name=collection_name,
                embedding_function=embedding_function # Use our pre-loaded function
            )
            logging.info(f"ChromaDB collection '{collection_name}' loaded/created for session {self.session_id}.")
        except Exception as e:
            logging.error(f"FATAL: Failed to initialize ChromaDB for session {self.session_id}: {e}")
            self.collection = None

    def add_turn(self, role, content):
        """
        Adds a new turn to the memory, updating both Tier 1 and Tier 3.
        Role is 'user' or 'model'.
        """
        import time # Add time import for timestamp

        # Tier 1: Update Conversational Buffer
        turn = {"role": role, "parts": [{'text': content}]} # Correctly format the turn
        self.conversational_buffer.append(turn)
        if len(self.conversational_buffer) > self.max_buffer_size:
            self.conversational_buffer.pop(0)

        # Tier 3: Add to Vector Store
        if self.collection:
            try:
                doc_id = str(uuid.uuid4())
                # --- NEW: Add timestamp to metadata ---
                metadata = {'role': role, 'timestamp': time.time()}
                
                # Storing 'role: content' for better semantic meaning
                doc_content = f"{role}: {content}"
                
                self.collection.add(
                    documents=[doc_content],
                    metadatas=[metadata],
                    ids=[doc_id]
                )
                logging.info(f"Successfully added document to ChromaDB collection for session {self.session_id}.")
            except Exception as e:
                logging.error(f"Could not add document to ChromaDB for session {self.session_id}: {e}")

    def get_context_for_prompt(self, prompt, n_results=3):
        """
        Retrieves relevant historical conversations from the vector store (Tier 3).
        """
        if not self.collection or self.collection.count() == 0:
            return []

        try:
            query_results = self.collection.query(
                query_texts=[prompt],
                n_results=min(n_results, self.collection.count())
            )
            
            if query_results and query_results['documents']:
                logging.info(f"Retrieved {len(query_results['documents'][0])} relevant docs from ChromaDB.")
                return query_results['documents'][0]
            return []
        except Exception as e:
            logging.error(f"Could not query ChromaDB for session {self.session_id}: {e}")
            return []

    def get_full_history(self):
        """Returns the conversational buffer (Tier 1) for the chat history."""
        return self.conversational_buffer
        
    def clear(self):
        """Clears the memory for the session by deleting the collection."""
        self.conversational_buffer = []
        if self.collection:
            try:
                collection_name = self.collection.name
                self.chroma_client.delete_collection(name=collection_name)
                logging.info(f"Cleared and deleted ChromaDB collection: {collection_name}")
            except Exception as e:
                logging.error(f"Error while clearing collection {self.collection.name}: {e}")
