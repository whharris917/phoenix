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
    Tier 2: Summaries & Segments (Mid-Term Memory) - NEW
    Tier 3: Vector Store (Long-Term, Specific Recall) # NOT CURRENTLY OPERATIONAL
    """
    def __init__(self, session_name):
        """
        Initializes the MemoryManager for a given session NAME.
        This will create or load a persistent ChromaDB collection based on the name.
        """
        self.session_name = session_name
        self.max_buffer_size = 30 # Increased buffer size for better context

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

        except Exception as e:
            logging.error(f"FATAL: Failed to initialize ChromaDB for session '{self.session_name}': {e}")
            self.collection = None

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

            self.conversational_buffer = [
                {"role": turn['metadata']['role'], "parts": [{'text': turn['document']}]}
                for turn in recent_turns
            ]
            logging.info(f"Repopulated buffer with {len(self.conversational_buffer)} turns from ChromaDB for session '{self.session_name}'.")

        except Exception as e:
            logging.error(f"Could not repopulate buffer from ChromaDB for session '{self.session_name}': {e}")
            self.conversational_buffer = []

    def add_turn(self, role, content, metadata=None):
        """
        Adds a new turn to the memory, updating both Tier 1 and Tier 3.
        Role is 'user' or 'model'.
        Metadata is an optional dictionary for storing additional info like summaries.
        """
        turn = {"role": role, "parts": [{'text': content}]}
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

                self.collection.add(
                    documents=[content], # Store the raw content directly as the document
                    metadatas=[meta],
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

    def get_unsummarized_turns(self):
        """
        Retrieves all turns that have not yet been included in a summary.
        This is the source material for creating a new Tier 2 summary.
        """
        all_turns = self.get_all_turns()
        unsummarized = [
            turn for turn in all_turns
            if not turn['metadata'].get('is_summarized') and turn['metadata'].get('role') in ['user', 'model']
        ]
        # Sort chronologically to ensure summary is logical
        unsummarized.sort(key=lambda x: x['metadata'].get('timestamp', 0))
        return unsummarized

    def add_summary_and_update_originals(self, summary_text, original_turn_ids):
        """
        Adds a new summary document (Tier 2) and marks the original turns (Tier 1)
        as summarized to prevent re-processing.

        Args:
            summary_text: The text of the summary to be added.
            original_turn_ids: A list of the IDs of the documents that were summarized.
        """
        if not self.collection:
            logging.error("Cannot add summary: collection is not initialized.")
            return

        # 1. Add the new summary document
        summary_id = str(uuid.uuid4())
        # Note: Summaries themselves are not marked as 'is_summarized'.
        summary_meta = {'role': 'summary', 'timestamp': time.time()}
        try:
            self.collection.add(
                documents=[summary_text],
                metadatas=[summary_meta],
                ids=[summary_id]
            )
            logging.info(f"Added Tier 2 summary to ChromaDB for session '{self.session_name}'.")
        except Exception as e:
            logging.error(f"Could not add summary document to ChromaDB: {e}")
            return # Don't mark originals if summary fails

        # 2. Update the original documents to mark them as summarized
        if original_turn_ids:
            existing_docs = self.collection.get(ids=original_turn_ids, include=['metadatas'])
            updated_metadatas = []
            if existing_docs and existing_docs['metadatas']:
                for meta in existing_docs['metadatas']:
                    meta['is_summarized'] = True
                    updated_metadatas.append(meta)
                self.update_turns_metadata(ids=original_turn_ids, metadatas=updated_metadatas)

    def get_recent_summaries(self, n_results=3):
        """
        Retrieves the N most recent summary documents to provide high-level context.
        """
        if not self.collection or self.collection.count() == 0:
            return []
        try:
            summaries = self.collection.get(where={"role": "summary"}, include=["documents", "metadatas"])
            if not summaries or not summaries.get('ids'): return []
            
            # Combine documents with their metadata, sort by timestamp, then return the top N documents
            combined_summaries = sorted(zip(summaries['documents'], summaries['metadatas']), key=lambda item: item[1]['timestamp'], reverse=True)
            return [doc for doc, meta in combined_summaries[:n_results]]
        except Exception as e:
            logging.error(f"Could not retrieve recent summaries from ChromaDB: {e}")
            return []