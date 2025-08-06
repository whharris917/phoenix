"""
Manages the agent's memory, including conversational history and long-term
vector storage using ChromaDB.

This module implements a Tiered Memory Architecture:
- Tier 1: A short-term "working memory" in the form of a conversational buffer.
- Tier 2: A long-term, searchable "reference memory" in a ChromaDB vector store.
It also encapsulates the logic for Retrieval-Augmented Generation (RAG).
"""

import chromadb
import logging
import uuid
import time
from vertexai.generative_models import Content, Part
import chromadb.utils.embedding_functions as embedding_functions
from config import CHROMA_DB_PATH
from data_models import MemoryRecord
from typing import List, Any
from typing import Optional

# --- Global Setup ---
# Initialize the embedding function once to be reused across all ChromaDBStore instances.
try:
    embedding_function = embedding_functions.DefaultEmbeddingFunction()
    logging.info("Successfully initialized the default sentence-transformer embedding model.")
except Exception as e:
    logging.critical(f"FATAL: Failed to initialize the embedding model: {e}")
    embedding_function = None


class ChromaDBStore:
    """
    Handles all direct read/write interactions with a specific ChromaDB collection.
    This class acts as a Data Access Layer (DAL), abstracting away the specifics
    of the ChromaDB library from the main memory management logic.
    """

    def __init__(self, collection_name: str):
        self.name = collection_name
        self.collection = None

        if embedding_function is None:
            logging.error(f"Cannot initialize ChromaDBStore for '{self.name}': embedding function not available.")
            return

        try:
            # Establishes a persistent client connection to the database on disk.
            chroma_client = chromadb.PersistentClient(path=CHROMA_DB_PATH)
            # Sanitize the collection name to meet ChromaDB's requirements.
            sanitized_name = "".join(c for c in self.name if c.isalnum() or c in ["_", "-"]).strip()
            if len(sanitized_name) < 3:
                sanitized_name = f"collection-{sanitized_name}-{uuid.uuid4().hex[:8]}"
            self.name = sanitized_name[:63] # Enforce max length.

            self.collection = chroma_client.get_or_create_collection(name=self.name, embedding_function=embedding_function)
            logging.info(f"ChromaDBStore connected to collection '{self.name}'.")
        except Exception as e:
            logging.error(f"FATAL: Failed to initialize ChromaDBStore for collection '{self.name}': {e}")

    def add_record(self, record: MemoryRecord, record_id: str) -> None:
        """Adds a single MemoryRecord to the collection."""
        if not self.collection:
            return
        try:
            # We store all fields except the document itself and its ID in the metadata.
            meta_dict = record.model_dump(exclude={"id", "document"}, exclude_none=True)
            self.collection.add(documents=[record.document], metadatas=[meta_dict], ids=[record_id])
        except Exception as e:
            logging.error(f"Could not add record to collection '{self.name}': {e}")

    def get_all_records(self) -> List[MemoryRecord]:
        """Retrieves and validates all records from the collection, sorted by time."""
        if not self.collection or self.collection.count() == 0:
            return []
        try:
            # Retrieve all data from the collection.
            history = self.collection.get(include=["metadatas", "documents"])
            if not history or not history.get("ids"):
                return []

            all_records = []
            # Reconstruct Pydantic models from the raw database dictionaries.
            for i, doc_id in enumerate(history["ids"]):
                meta_dict = history["metadatas"][i]
                full_record_dict = {"id": doc_id, "document": history["documents"][i], **meta_dict}
                try:
                    # Validate each record against the MemoryRecord schema.
                    all_records.append(MemoryRecord.model_validate(full_record_dict))
                except Exception as validation_error:
                    # This prevents one corrupted record from crashing the entire process.
                    logging.warning(f"Skipping record in collection '{self.name}' due to validation error: {validation_error}")

            # Ensure the history is in chronological order.
            all_records.sort(key=lambda x: x.timestamp)
            return all_records
        except Exception as e:
            logging.error(f"Could not retrieve records from collection '{self.name}': {e}")
            return []

    def query(self, query_text: str, n_results: int = 5) -> List[MemoryRecord]:
        """Queries the collection for similar documents and returns validated records."""
        if not self.collection or self.collection.count() == 0:
            return []
        try:
            # Perform the vector similarity search.
            query_results = self.collection.query(
                query_texts=[query_text],
                n_results=min(n_results, self.collection.count()), # Cannot request more results than exist.
                include=["documents", "metadatas"],
            )
            if not query_results or not query_results.get("ids", [[]])[0]:
                return []

            results_with_meta = []
            # Reconstruct Pydantic models from the query results.
            for i, doc_id in enumerate(query_results["ids"][0]):
                meta_dict = query_results["metadatas"][0][i]
                full_record_dict = {"id": doc_id, "document": query_results["documents"][0][i], **meta_dict}
                try:
                    results_with_meta.append(MemoryRecord.model_validate(full_record_dict))
                except Exception as validation_error:
                    logging.warning(f"Skipping record in query for '{self.name}' due to validation error: {validation_error}")

            # Sort the retrieved chunks chronologically for better contextual flow.
            results_with_meta.sort(key=lambda x: x.timestamp)
            return results_with_meta
        except Exception as e:
            logging.error(f"Could not query collection '{self.name}': {e}")
            return []

    def update_records_metadata(self, ids: List[str], metadatas: List[dict]):
        """Updates metadata for existing records in the collection."""
        if not self.collection:
            return
        try:
            self.collection.update(ids=ids, metadatas=metadatas)
        except Exception as e:
            logging.error(f"Could not update metadata in collection '{self.name}': {e}")

    def delete_collection(self):
        """Deletes the entire collection from the database."""
        if not self.collection:
            return
        try:
            chroma_client = chromadb.PersistentClient(path=CHROMA_DB_PATH)
            chroma_client.delete_collection(name=self.name)
            logging.info(f"Deleted ChromaDB collection: {self.name}")
        except Exception as e:
            logging.error(f"Error deleting collection {self.name}: {e}")


class MemoryManager:
    """
    Manages the Tiered Memory Architecture for the AI agent by orchestrating
    the conversational buffer and the long-term vector store. This is the main
    high-level interface for the rest of the application to interact with memory.
    """

    def __init__(self, session_name: str):
        self.session_name = session_name
        self.max_buffer_size = 10 # Defines the size of the short-term working memory.
        self.conversational_buffer: List[Content] = []

        # Creates instances of the data layer for different types of memory.
        self.turn_store = ChromaDBStore(collection_name=f"turns-{session_name}")
        self.code_store = ChromaDBStore(collection_name=f"code-{session_name}")

        # On initialization, rehydrate the working memory from the database.
        self._repopulate_buffer_from_db()

    def _repopulate_buffer_from_db(self):
        """Loads the most recent history from the DB into the conversational buffer."""
        all_turns = self.turn_store.get_all_records()
        if not all_turns:
            return
        try:
            recent_turns = all_turns[-self.max_buffer_size :]
            self.conversational_buffer = [Content(role=turn.role, parts=[Part.from_text(turn.document)]) for turn in recent_turns if turn.role]
            logging.info(f"Repopulated buffer with {len(self.conversational_buffer)} turns for session '{self.session_name}'.")
        except Exception as e:
            logging.error(f"Could not repopulate buffer for session '{self.session_name}': {e}")
            self.conversational_buffer = []

    def add_turn(self, role: str, content: str, metadata: dict = None, augmented_prompt: str = None):
        """Adds a new turn to both the buffer (Tier 1) and vector store (Tier 2)."""
        # Add to the short-term buffer.
        turn = Content(role=role, parts=[Part.from_text(content)])
        self.conversational_buffer.append(turn)
        # Trim the buffer if it exceeds the max size.
        if len(self.conversational_buffer) > self.max_buffer_size:
            self.conversational_buffer.pop(0)

        # Create a standardized record for long-term storage.
        record = MemoryRecord(
            role=role, timestamp=time.time(), document=content,
            augmented_prompt=augmented_prompt, raw_content=content
        )
        if metadata:
            for key, value in metadata.items():
                if hasattr(record, key):
                    setattr(record, key, value)
        
        # Delegate persistence to the data store.
        self.turn_store.add_record(record, str(record.id))
        logging.info(f"Added turn to memory for session '{self.session_name}' with id: {record.id}")

    def get_all_turns(self) -> List[MemoryRecord]:
        """Delegates retrieval of all turns to the data store."""
        return self.turn_store.get_all_records()

    def get_context_for_prompt(self, prompt: str, n_results: int = 5) -> List[MemoryRecord]:
        """Delegates context retrieval (vector search) to the data store."""
        return self.turn_store.query(prompt, n_results)

    def get_conversational_buffer(self) -> List[Content]:
        """Returns the short-term conversational buffer for the chat history."""
        return self.conversational_buffer
        
    def prepare_augmented_prompt(self, prompt: str) -> str:
        """
        Retrieves relevant context from memory and constructs an augmented prompt.

        This method encapsulates the RAG (Retrieval-Augmented Generation) logic.
        It finds relevant past conversations and injects them as context into the
        current prompt for the model.

        Args:
            prompt: The user's current prompt.

        Returns:
            The final prompt string, augmented with context if any was found.
        """
        # Tier 2 Memory Retrieval: Perform a vector search for relevant context.
        retrieved_context = self.get_context_for_prompt(prompt)
        final_prompt = prompt

        if retrieved_context:
            # Format the retrieved documents into a context block.
            context_str = "\n".join(f"- {item.role}: {item.document}" for item in retrieved_context if item.role)
            final_prompt = (
                "CONTEXT FROM PAST CONVERSATIONS (IN CHRONOLOGICAL ORDER):\n"
                f"{context_str}\n\n"
                "--- CURRENT TASK ---\n"
                "Based on the above context, please respond to the following prompt:\n"
                f"{prompt}"
            )
            log_message = f"Augmented prompt with {len(retrieved_context)} documents from memory."
            logging.info(log_message)
        
        return final_prompt

    def delete_memory_collection(self):
        """Deletes the entire memory for the session from all data stores."""
        self.conversational_buffer = []
        self.turn_store.delete_collection()
        self.code_store.delete_collection()
        logging.info(f"Deleted memory collections for session '{self.session_name}'")

    def add_code_artifact(self, filename: str, content: str) -> Optional[str]:
        """Saves a code artifact to a dedicated vector store and returns a pointer ID."""
        record = MemoryRecord(
            type="code_artifact", timestamp=time.time(),
            document=f"Content of file: {filename}",
            raw_content=content, filename=filename
        )
        # The pointer is a unique, identifiable string that can be placed in prose.
        pointer_id = f"[CODE-ARTIFACT-{record.id}:{filename}]"

        self.code_store.add_record(record, pointer_id)
        logging.info(f"Saved code artifact with pointer: {pointer_id}")
        return pointer_id
