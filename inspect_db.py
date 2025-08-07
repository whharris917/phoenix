import chromadb
import os
import pandas as pd
import json
from datetime import datetime
from tracer import trace

from memory_manager import ChromaDBStore
from config import CHROMA_DB_PATH

@trace
def get_db_client():
    """Initializes and returns a ChromaDB client."""
    if not os.path.exists(CHROMA_DB_PATH):
        raise FileNotFoundError("ChromaDB directory not found.")
    return chromadb.PersistentClient(path=CHROMA_DB_PATH)

@trace
def list_collections_as_json():
    """Lists all collections, finds their last modified time, sorts them, and returns them as a JSON string."""
    try:
        client = get_db_client()
        collections = client.list_collections()
        collection_list = []
        for col in collections:
            last_modified = 0
            # Getting all metadata just to find the max timestamp is inefficient.
            # A better approach would be to store this as a property if needed frequently.
            # For this tool, we'll keep the existing logic.
            metadata = col.get(include=["metadatas"]).get("metadatas")
            if metadata:
                timestamps = [m.get("timestamp", 0) for m in metadata if m]
                if timestamps:
                    last_modified = max(timestamps)

            collection_list.append({"name": col.name, "count": col.count(), "last_modified": last_modified})

        collection_list.sort(key=lambda x: x["last_modified"], reverse=True)
        return json.dumps({"status": "success", "collections": collection_list})
    except Exception as e:
        return json.dumps({"status": "error", "message": str(e)})

@trace
def get_collection_data_as_json(collection_name):
    """Retrieves all data from a specific collection and returns it as a JSON string."""
    try:
        # REFACTORED: Use ChromaDBStore to fetch and validate all records.
        db_store = ChromaDBStore(collection_name=collection_name)
        all_records = db_store.get_all_records()

        if not all_records:
            return json.dumps({"status": "success", "collection_name": collection_name, "data": []})

        formatted_data = []
        for record in all_records:
            # REFACTORED: Build the frontend dict from the validated MemoryRecord object.
            try:
                readable_time = datetime.fromtimestamp(record.timestamp).strftime("%Y-%m-%d %H:%M:%S") if record.timestamp else "N/A"
            except (ValueError, TypeError):
                readable_time = "Invalid Timestamp"

            formatted_data.append(
                {
                    "ID": str(record.id),
                    "Timestamp": readable_time,
                    "Role": record.role,
                    "Summary": record.summary,
                    "Augmented Prompt": record.augmented_prompt,
                    "Type": record.type,
                    "Segment ID": str(record.segment_id) if record.segment_id else None,
                    "Document (Memory Content)": record.raw_content or record.document,
                }
            )

        formatted_data.sort(key=lambda x: x.get("Timestamp", ""), reverse=True)
        return json.dumps(
            {
                "status": "success",
                "collection_name": collection_name,
                "data": formatted_data,
            }
        )
    except Exception as e:
        return json.dumps(
            {
                "status": "error",
                "message": f"Failed to retrieve collection '{collection_name}': {e}",
            }
        )

@trace
def inspect_database_cli():
    # This function remains unchanged as it only uses the public JSON-producing functions.
    print("--- ChromaDB Inspector (CLI) ---")
    try:
        collections_json = json.loads(list_collections_as_json())
        if collections_json["status"] == "error":
            print(f"Error: {collections_json['message']}")
            return

        collections = collections_json["collections"]
        if not collections:
            print("No collections (sessions) found in the database.")
            return

        print("Available Collections (Sessions):")
        for i, collection in enumerate(collections):
            print(f"  {i + 1}. {collection['name']} (Documents: {collection['count']})")

        while True:
            try:
                choice = int(input("\\nEnter the number of the collection to inspect: "))
                if 1 <= choice <= len(collections):
                    selected_collection_name = collections[choice - 1]["name"]
                    break
                else:
                    print("Invalid choice. Please try again.")
            except (ValueError, IndexError):
                print("Invalid input. Please enter a number from the list.")

        print(f"\\n--- Inspecting Collection: {selected_collection_name} ---")
        data_json = json.loads(get_collection_data_as_json(selected_collection_name))

        if data_json["status"] == "error":
            print(f"Error: {data_json['message']}")
            return

        if not data_json["data"]:
            print("This collection is empty.")
            return

        df = pd.DataFrame(data_json["data"])
        pd.set_option("display.max_rows", None)
        pd.set_option("display.max_colwidth", None)
        pd.set_option("display.width", 1000)
        print(df)

    except Exception as e:
        print(f"\\nAn unexpected error occurred: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    inspect_database_cli()
