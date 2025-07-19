import chromadb
import logging
import uuid
import os
import time
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
    def __init__(self, session_name):
        """
        Initializes the MemoryManager for a given session NAME.
        This will create or load a persistent ChromaDB collection based on the name.
        """
        self.session_name = session_name
        self.max_buffer_size = 20 # Increased buffer size for better context

        # Tier 1: Conversational Buffer
        self.conversational_buffer = []

        # Tier 3: Vector Store (ChromaDB)
        if embedding_function is None:
            logging.error(f"Cannot initialize ChromaDB for session '{self.session_name}' because embedding function failed to load.")
            self.collection = None
            return

        try:
            self.chroma_client = chromadb.PersistentClient(path=CHROMA_DB_PATH)

            # Sanitize session_name to be a valid ChromaDB collection name.
            # A valid name contains only alphanumeric characters, dots, dashes, and underscores,
            # and is between 3 and 63 characters long.
            sanitized_name = "".join(c for c in self.session_name if c.isalnum() or c in ['_', '-']).strip()
            if len(sanitized_name) < 3:
                sanitized_name = f"session-{sanitized_name}-{uuid.uuid4().hex[:8]}"
            collection_name = sanitized_name[:63] # Enforce max length

            self.collection = self.chroma_client.get_or_create_collection(
                name=collection_name,
                embedding_function=embedding_function
            )
            logging.info(f"ChromaDB collection '{collection_name}' loaded/created for session '{self.session_name}'.")

            # --- NEW: Repopulate buffer from DB on init ---
            self._repopulate_buffer_from_db()

        except Exception as e:
            logging.error(f"FATAL: Failed to initialize ChromaDB for session '{self.session_name}': {e}")
            self.collection = None

    def _repopulate_buffer_from_db(self):
        """
        Loads the most recent history from the ChromaDB collection into the
        conversational buffer to maintain context across sessions.
        """
        if not self.collection or self.collection.count() == 0:
            logging.info(f"No history found in ChromaDB for session '{self.session_name}'.")
            return

        try:
            history = self.collection.get(include=["metadatas", "documents"])

            if not history or not history.get('ids'):
                return

            combined_history = []
            for i, doc_id in enumerate(history['ids']):
                meta = history['metadatas'][i]
                doc = history['documents'][i]

                try:
                    # Document format is "role: content"
                    role, content = doc.split(":", 1)
                    content = content.strip()
                    # Use the role from metadata if available, as it's more reliable
                    role_to_use = meta.get('role', role)
                    if role_to_use not in ['user', 'model']:
                        logging.warning(f"Skipping document with invalid role '{role_to_use}' in session '{self.session_name}'.")
                        continue
                except ValueError:
                    logging.warning(f"Skipping malformed document in DB: {doc}")
                    continue

                combined_history.append({
                    'role': role_to_use,
                    'timestamp': meta.get('timestamp', 0),
                    'content': content
                })

            combined_history.sort(key=lambda x: x['timestamp'], reverse=True)
            recent_turns = combined_history[:self.max_buffer_size]
            recent_turns.reverse()

            self.conversational_buffer = [
                {"role": turn['role'], "parts": [{'text': turn['content']}]}
                for turn in recent_turns
            ]

            logging.info(f"Repopulated buffer with {len(self.conversational_buffer)} turns from ChromaDB for session '{self.session_name}'.")

        except Exception as e:
            logging.error(f"Could not repopulate buffer from ChromaDB for session '{self.session_name}': {e}")
            self.conversational_buffer = []

    def add_turn(self, role, content):
        """
        Adds a new turn to the memory, updating both Tier 1 and Tier 3.
        Role is 'user' or 'model'.
        """
        turn = {"role": role, "parts": [{'text': content}]}
        self.conversational_buffer.append(turn)
        if len(self.conversational_buffer) > self.max_buffer_size:
            self.conversational_buffer.pop(0)

        if self.collection:
            try:
                doc_id = str(uuid.uuid4())
                metadata = {'role': role, 'timestamp': time.time()}
                doc_content = f"{role}: {content}"

                self.collection.add(
                    documents=[doc_content],
                    metadatas=[metadata],
                    ids=[doc_id]
                )
                logging.info(f"Added document to ChromaDB for session '{self.session_name}'.")
            except Exception as e:
                logging.error(f"Could not add document to ChromaDB for session '{self.session_name}': {e}")

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
                logging.info(f"Retrieved {len(query_results['documents'][0])} docs from ChromaDB for session '{self.session_name}'.")
                return query_results['documents'][0]
            return []
        except Exception as e:
            logging.error(f"Could not query ChromaDB for session '{self.session_name}': {e}")
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
                logging.info(f"Cleared and deleted ChromaDB collection: {collection_name} for session '{self.session_name}'")
            except Exception as e:
                logging.error(f"Error clearing collection {self.collection.name} for session '{self.session_name}': {e}")
