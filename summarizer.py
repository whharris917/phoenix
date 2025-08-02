import chromadb
import time
import logging
import uuid  # Import uuid for segment IDs
from datetime import datetime, timezone
from vertexai.generative_models import GenerativeModel, Part
import vertexai
from config import (
    SUMMARIZER_MODEL_NAME,
    SEGMENT_THRESHOLD,
    PROJECT_ID,
    LOCATION,
    CHROMA_DB_PATH,
)

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - Summarizer - %(levelname)s - %(message)s"
)


def main():
    """The main loop for the summarization background process."""

    # --- Initialize Vertex AI and the summarizer model ---
    vertexai.init(project=PROJECT_ID, location=LOCATION)
    summarizer_model = GenerativeModel(SUMMARIZER_MODEL_NAME)

    # --- Initialize ChromaDB client ---
    chroma_client = chromadb.PersistentClient(path=CHROMA_DB_PATH)
    logging.info("Summarizer connected to ChromaDB.")

    # Define your date cutoff here
    cutoff_date = datetime(2025, 7, 31, tzinfo=timezone.utc)
    cutoff_timestamp = cutoff_date.timestamp()

    while True:
        try:
            collections = chroma_client.list_collections()

            for collection in collections:
                # Check the collection's last modified date
                metadata_for_check = collection.get(include=["metadatas"]).get(
                    "metadatas"
                )
                last_modified = 0
                if metadata_for_check:
                    timestamps = [
                        m.get("timestamp", 0) for m in metadata_for_check if m
                    ]
                    if timestamps:
                        last_modified = max(timestamps)

                if last_modified < cutoff_timestamp:
                    logging.info(
                        f"Skipping collection '{collection.name}' as it was last modified before the cutoff date."
                    )
                    continue

                # --- Part 1: Per-Turn Summarization ---
                history = collection.get(include=["metadatas", "documents"])
                unsummarized_ids = []
                unsummarized_docs = []
                unsummarized_metas = []

                for i, meta in enumerate(history["metadatas"]):
                    if "summary" not in meta:
                        unsummarized_ids.append(history["ids"][i])
                        unsummarized_docs.append(history["documents"][i])
                        unsummarized_metas.append(meta)

                # MODIFIED: Wrap the per-turn summarizer in an 'if' block and remove the 'continue'.
                if unsummarized_ids:
                    logging.info(
                        f"Found {len(unsummarized_ids)} turns to summarize in '{collection.name}'."
                    )
                    # This loop now only runs if there is work to do.
                    for i, doc_id in enumerate(unsummarized_ids):
                        doc_content = unsummarized_docs[i]
                        original_meta = unsummarized_metas[i]

                        prompt = f"Concisely summarize the following text, capturing its core intent and key information:\n\n---\n{doc_content}\n---"
                        response = summarizer_model.generate_content(
                            [Part.from_text(prompt)]
                        )
                        summary_text = response.text.strip()

                        updated_meta = {
                            "role": original_meta.get("role"),
                            "timestamp": original_meta.get("timestamp"),
                            "augmented_prompt": original_meta.get("augmented_prompt"),
                            "summary": summary_text,
                            "raw_content": doc_content,
                        }
                        updated_meta = {
                            k: v for k, v in updated_meta.items() if v is not None
                        }

                        collection.update(
                            ids=[doc_id],
                            documents=[summary_text],
                            metadatas=[updated_meta],
                        )
                        logging.info(f"Updated doc {doc_id} with summary.")
                        time.sleep(1)

                # --- NEW: Part 2: Segment Summarization Logic ---
                # Re-fetch history to include the turns we just summarized
                current_history = collection.get(include=["metadatas", "documents"])

                # Find all turns that have a summary but no segment_id
                unsegmented_turns = [
                    # We need the full metadata dictionary, so we get 'meta'
                    {"id": current_history["ids"][i], "meta": meta}
                    for i, meta in enumerate(current_history["metadatas"])
                    if meta.get("summary") and not meta.get("segment_id")
                ]

                if len(unsegmented_turns) >= SEGMENT_THRESHOLD:
                    logging.info(
                        f"Threshold met. Creating a new segment for {len(unsegmented_turns)} turns in '{collection.name}'."
                    )

                    segment_id = str(uuid.uuid4())

                    unsegmented_turns.sort(key=lambda x: x["meta"].get("timestamp", 0))

                    summaries_to_process = "\n".join(
                        [f"- {turn['meta']['summary']}" for turn in unsegmented_turns]
                    )

                    prompt = f"The following is a sequence of conversational summaries. Please provide a single-paragraph 'chapter summary' that describes the overall topic, progress, and outcome of this conversational segment.\n\n---\n{summaries_to_process}\n---"

                    response = summarizer_model.generate_content(
                        [Part.from_text(prompt)]
                    )
                    segment_summary_text = response.text.strip()

                    # 1. Add the new segment summary as its own document
                    collection.add(
                        ids=[segment_id],
                        documents=[segment_summary_text],
                        metadatas=[
                            {"type": "segment_summary", "timestamp": time.time()}
                        ],
                    )
                    logging.info(f"Added new segment summary {segment_id}.")

                    # --- MODIFIED: More robust back-linking logic ---
                    # 2. Back-link all individual turns to this new segment_id
                    ids_to_update = [turn["id"] for turn in unsegmented_turns]

                    # Explicitly create a new list of new, updated metadata dictionaries
                    updated_metadatas = []
                    for turn in unsegmented_turns:
                        new_meta = turn[
                            "meta"
                        ].copy()  # Start with a copy of the old metadata
                        new_meta["segment_id"] = segment_id  # Add the new segment ID
                        updated_metadatas.append(new_meta)

                    collection.update(
                        ids=ids_to_update,
                        metadatas=updated_metadatas,  # Use the new, explicitly created list
                    )
                    logging.info(
                        f"Tagged {len(ids_to_update)} turns with segment_id {segment_id}."
                    )

        except Exception as e:
            logging.error(f"An error occurred in the summarizer loop: {e}")

        logging.info("Summarization cycle complete. Sleeping for 60 seconds.")
        time.sleep(60)


if __name__ == "__main__":
    main()
