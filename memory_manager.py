import chromadb
import logging
import uuid
import os
import time
from vertexai.generative_models import Content, Part
import chromadb.utils.embedding_functions as embedding_functions

# This script will be in the project root. The sandbox is a subdirectory.
SANDBOX_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.sandbox')
CHROMA_DB_PATH = os.path.join(SANDBOX_DIR, 'chroma_db')

# Ensure the ChromaDB directory exists
os.makedirs(CHROMA_DB_PATH, exist_ok=True)
logging.info(f"ChromaDB path set to: {CHROMA_DB_PATH}")


# --- Explicitly define the embedding function ---
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
    Tier 2: Summaries & Segments (Mid-Term Memory)
    Tier 3: Vector Store (Long-Term, Specific Recall)
    """
    def __init__(self, session_name):
        """
        Initializes the MemoryManager for a given session NAME.
        This will create or load a persistent ChromaDB collection based on the name.
        """
        self.session_name = session_name
        self.max_buffer_size = 10

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

            # Repopulate buffer from DB on init
            self._repopulate_buffer_from_db()
            
            # NEW: Create a dedicated collection for code artifacts
            code_collection_name = f"code-{collection_name}"
            self.code_collection = self.chroma_client.get_or_create_collection(
                name=code_collection_name,
                embedding_function=embedding_function
            )
            logging.info(f"ChromaDB code collection '{code_collection_name}' loaded/created.")

        except Exception as e:
            logging.error(f"FATAL: Failed to initialize ChromaDB for session '{self.session_name}': {e}")
            self.collection = None
            self.code_collection = None # NEW

    def _repopulate_buffer_from_db(self):
        """
        Loads the most recent history from the ChromaDB collection into the
        conversational buffer to maintain context across sessions.
        """
        all_turns = self.get_all_turns()
        if not all_turns:
            return

        try:
            # Sort by timestamp, most recent first
            all_turns.sort(key=lambda x: x['metadata'].get('timestamp', 0), reverse=True)
            # Take the most recent turns up to the buffer size
            recent_turns = all_turns[:self.max_buffer_size]
            # Reverse again to get chronological order
            recent_turns.reverse()

            # --- Create Content objects using Part.from_text() ---
            self.conversational_buffer = [
                Content(role=turn['metadata']['role'], parts=[Part.from_text(turn['document'])])
                for turn in recent_turns
            ]
            logging.info(f"Repopulated buffer with {len(self.conversational_buffer)} turns from ChromaDB for session '{self.session_name}'.")

        except Exception as e:
            logging.error(f"Could not repopulate buffer from ChromaDB for session '{self.session_name}': {e}")
            self.conversational_buffer = []

    def add_turn(self, role, content, metadata=None, augmented_prompt=None):
            """
            Adds a new turn to the memory, updating both Tier 1 and Tier 3.
            Role is 'user' or 'model'.
            Metadata is an optional dictionary for storing additional info.
            augmented_prompt is the full prompt including RAG context.
            """
            turn = Content(role=role, parts=[Part.from_text(content)])
            self.conversational_buffer.append(turn)
            if len(self.conversational_buffer) > self.max_buffer_size:
                self.conversational_buffer.pop(0)

            if self.collection:
                try:
                    doc_id = str(uuid.uuid4())
                    
                    # Start with base metadata and update with any provided metadata
                    meta = {'role': role, 'timestamp': time.time()}
                    if metadata:
                        meta.update(metadata)
                    
                    # NEW: Add the augmented prompt to the metadata if it exists
                    if augmented_prompt:
                        meta['augmented_prompt'] = augmented_prompt

                    self.collection.add(
                        documents=[content], # The document remains the clean, base content
                        metadatas=[meta],    # The metadata now contains the full context
                        ids=[doc_id]
                    )
                    logging.info(f"Added document to ChromaDB for session '{self.session_name}' with metadata: {meta}")
                except Exception as e:
                    logging.error(f"Could not add document to ChromaDB for session '{self.session_name}': {e}")
    
    # --- Function to update existing records ---
    def update_turns_metadata(self, ids, metadatas):
        """
        Updates the metadata for one or more existing documents in the collection.
        'ids' is a list of document IDs to update.
        'metadatas' is a list of corresponding metadata dictionaries.
        """
        if not self.collection:
            logging.error("Cannot update metadata: collection is not initialized.")
            return
        try:
            self.collection.update(ids=ids, metadatas=metadatas)
            logging.info(f"Updated metadata for {len(ids)} documents in ChromaDB for session '{self.session_name}'.")
        except Exception as e:
            logging.error(f"Could not update metadata in ChromaDB for session '{self.session_name}': {e}")

    # --- NEW: Function to get all turns for summarization ---
    def get_all_turns(self):
        """
        Retrieves all documents, metadatas, and IDs from the collection.
        Returns a list of dictionaries, each representing a turn.
        """
        if not self.collection or self.collection.count() == 0:
            return []
        
        try:
            history = self.collection.get(include=["metadatas", "documents"])
            if not history or not history.get('ids'):
                return []
            
            # Re-structure the data into a more usable list of objects
            all_turns = []
            for i, doc_id in enumerate(history['ids']):
                all_turns.append({
                    "id": doc_id,
                    "document": history['documents'][i],
                    "metadata": history['metadatas'][i]
                })
            
            # Sort chronologically
            all_turns.sort(key=lambda x: x['metadata'].get('timestamp', 0))
            return all_turns

        except Exception as e:
            logging.error(f"Could not retrieve all turns from ChromaDB for session '{self.session_name}': {e}")
            return []

    def get_context_for_prompt(self, prompt, n_results=5): # Increased default results
        """
        Retrieves relevant historical conversations from the vector store,
        sorts them chronologically, and returns them.
        """
        if not self.collection or self.collection.count() == 0:
            return []

        try:
            # Step 1: Query ChromaDB including metadata
            query_results = self.collection.query(
                query_texts=[prompt],
                n_results=min(n_results, self.collection.count()),
                include=["documents", "metadatas"] # Crucially, include metadatas
            )

            if not query_results or not query_results.get('ids', [[]])[0]:
                return []

            # Step 2: Combine documents and metadata into a list of objects
            results_with_meta = []
            for i, doc_id in enumerate(query_results['ids'][0]):
                results_with_meta.append({
                    "id": doc_id,
                    "document": query_results['documents'][0][i],
                    "metadata": query_results['metadatas'][0][i]
                })

            # Step 3: Sort the results by timestamp (oldest to newest)
            results_with_meta.sort(key=lambda x: x['metadata'].get('timestamp', 0))

            logging.info(f"Retrieved and sorted {len(results_with_meta)} docs from ChromaDB for session '{self.session_name}'.")
            return results_with_meta

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

    # NEW: Method to add a code artifact and return a pointer
    def add_code_artifact(self, filename, content):
        """Saves a code artifact to the dedicated collection and returns a pointer."""
        if not self.code_collection:
            logging.error("Cannot add code artifact: code_collection is not initialized.")
            return None

        try:
            artifact_uuid = str(uuid.uuid4())
            pointer_id = f"[CODE-ARTIFACT-{artifact_uuid}:{filename}]"
            
            # We don't need to vectorize code for semantic search, so we store
            # the content in the metadata. The document can be a simple description.
            self.code_collection.add(
                documents=[f"Content of file: {filename}"],
                metadatas=[{'filename': filename, 'content': content, 'timestamp': time.time()}],
                ids=[pointer_id] # Use the pointer as the unique ID
            )
            logging.info(f"Saved code artifact with pointer: {pointer_id}")
            return pointer_id
        except Exception as e:
            logging.error(f"Could not add code artifact: {e}")
            return None
