import chromadb
import time
import logging
import uuid
from datetime import datetime, timezone
from vertexai.generative_models import GenerativeModel, Part
import vertexai

# REFACTORED: Import ChromaDBStore from the newly refactored memory_manager
from memory_manager import ChromaDBStore
from config import (
    SUMMARIZER_MODEL_NAME,
    SEGMENT_THRESHOLD,
    PROJECT_ID,
    LOCATION,
    CHROMA_DB_PATH,
)
from data_models import MemoryRecord

logging.basicConfig(level=logging.INFO, format="%(asctime)s - Summarizer - %(levelname)s - %(message)s")


def main():
    """The main loop for the summarization background process."""
    vertexai.init(project=PROJECT_ID, location=LOCATION)
    summarizer_model = GenerativeModel(SUMMARIZER_MODEL_NAME)
    chroma_client = chromadb.PersistentClient(path=CHROMA_DB_PATH)
    logging.info("Summarizer connected to ChromaDB.")

    cutoff_date = datetime(2025, 7, 31, tzinfo=timezone.utc)
    cutoff_timestamp = cutoff_date.timestamp()

    while True:
        try:
            all_collections = chroma_client.list_collections()
            # REFACTORED: Only process 'turns' collections, not 'code' collections.
            turn_collections = [c for c in all_collections if c.name.startswith("turns-")]

            for collection_summary in turn_collections:
                collection_name = collection_summary.name

                # REFACTORED: Instantiate ChromaDBStore to handle all DB interactions
                db_store = ChromaDBStore(collection_name=collection_name)
                if not db_store.collection:
                    logging.warning(f"Could not initialize store for collection '{collection_name}'. Skipping.")
                    continue

                all_records = db_store.get_all_records()

                if not all_records:
                    logging.info(f"Collection '{collection_name}' is empty. Skipping.")
                    continue

                last_modified = max(r.timestamp for r in all_records)

                if last_modified < cutoff_timestamp:
                    logging.info(f"Skipping collection '{collection_name}' as it was last modified before the cutoff date.")
                    continue

                # --- Part 1: Per-Turn Summarization ---
                unsummarized_records = [r for r in all_records if not r.summary]

                if unsummarized_records:
                    logging.info(f"Found {len(unsummarized_records)} turns to summarize in '{collection_name}'.")

                    ids_to_update, metadatas_to_update, documents_to_update = [], [], []
                    for record in unsummarized_records:
                        doc_content = record.raw_content or record.document
                        prompt = f"Concisely summarize the following text, capturing its core intent and key information:\n\n---\n{doc_content}\n---"
                        response = summarizer_model.generate_content([Part.from_text(prompt)])
                        summary_text = response.text.strip()

                        updated_record = record.model_copy(update={"summary": summary_text})

                        ids_to_update.append(str(record.id))
                        documents_to_update.append(summary_text)  # Main document becomes summary
                        metadatas_to_update.append(updated_record.model_dump(exclude={"id", "document"}, exclude_none=True))

                        logging.info(f"Summarized doc {record.id}.")
                        time.sleep(1)

                    db_store.update_records_metadata(ids=ids_to_update, metadatas=metadatas_to_update)
                    logging.info(f"Bulk updated {len(ids_to_update)} summaries in '{collection_name}'.")

                # --- Part 2: Segment Summarization Logic ---
                current_records = db_store.get_all_records()
                unsegmented_records = [r for r in current_records if r.summary and not r.segment_id]

                if len(unsegmented_records) >= SEGMENT_THRESHOLD:
                    logging.info(f"Threshold met. Creating a new segment for {len(unsegmented_records)} turns in '{collection_name}'.")
                    segment_id = uuid.uuid4()

                    summaries_to_process = "\n".join([f"- {r.summary}" for r in unsegmented_records])
                    prompt = f"The following is a sequence of conversational summaries. Please provide a single-paragraph 'chapter summary' that describes the overall topic, progress, and outcome of this conversational segment.\n\n---\n{summaries_to_process}\n---"

                    response = summarizer_model.generate_content([Part.from_text(prompt)])
                    segment_summary_text = response.text.strip()

                    summary_record = MemoryRecord(
                        id=segment_id,
                        type="segment_summary",
                        timestamp=time.time(),
                        document=segment_summary_text,
                    )
                    db_store.add_record(summary_record, str(summary_record.id))
                    logging.info(f"Added new segment summary {segment_id}.")

                    ids_to_update = [str(r.id) for r in unsegmented_records]
                    updated_metadatas = []
                    for record in unsegmented_records:
                        updated_record = record.model_copy(update={"segment_id": segment_id})
                        updated_metadatas.append(updated_record.model_dump(exclude={"id", "document"}, exclude_none=True))

                    db_store.update_records_metadata(ids=ids_to_update, metadatas=updated_metadatas)
                    logging.info(f"Tagged {len(ids_to_update)} turns with segment_id {segment_id}.")

        except Exception as e:
            logging.error(f"An error occurred in the summarizer loop: {e}", exc_info=True)

        logging.info("Summarization cycle complete. Sleeping for 60 seconds.")
        time.sleep(60)


if __name__ == "__main__":
    main()
