import chromadb
import os
import pandas as pd
import json
from datetime import datetime
from config import CHROMA_DB_PATH


def get_db_client():
    """Initializes and returns a ChromaDB client."""
    if not os.path.exists(CHROMA_DB_PATH):
        raise FileNotFoundError("ChromaDB directory not found.")
    return chromadb.PersistentClient(path=CHROMA_DB_PATH)


def list_collections_as_json():
    """
    Lists all collections, finds their last modified time, sorts them,
    and returns them as a JSON string.
    """
    try:
        client = get_db_client()
        collections = client.list_collections()

        collection_list = []
        for col in collections:
            last_modified = 0
            # Get all metadata to find the latest timestamp
            metadata = col.get(include=["metadatas"]).get("metadatas")
            if metadata:
                timestamps = [m.get("timestamp", 0) for m in metadata if m]
                if timestamps:
                    last_modified = max(timestamps)

            collection_list.append(
                {"name": col.name, "count": col.count(), "last_modified": last_modified}
            )

        # Sort collections by last_modified timestamp, descending
        collection_list.sort(key=lambda x: x["last_modified"], reverse=True)

        return json.dumps({"status": "success", "collections": collection_list})
    except Exception as e:
        return json.dumps({"status": "error", "message": str(e)})


def get_collection_data_as_json(collection_name):
    """Retrieves all data from a specific collection and returns it as a JSON string."""
    try:
        client = get_db_client()
        collection = client.get_collection(name=collection_name)
        # Ensure you include documents and metadatas
        data = collection.get(include=["metadatas", "documents"])

        if not data or not data["ids"]:
            return json.dumps(
                {"status": "success", "collection_name": collection_name, "data": []}
            )

        formatted_data = []
        for i, doc_id in enumerate(data["ids"]):
            metadata = (
                data["metadatas"][i]
                if data["metadatas"] and data["metadatas"][i]
                else {}
            )
            timestamp = metadata.get("timestamp", 0)

            try:
                readable_time = (
                    datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M:%S")
                    if timestamp
                    else "N/A"
                )
            except (ValueError, TypeError):
                readable_time = "Invalid Timestamp"

            # This block now includes all the fields we've added
            formatted_data.append(
                {
                    "ID": doc_id,
                    "Timestamp": readable_time,
                    "Role": metadata.get("role"),
                    "Summary": metadata.get("summary"),
                    "Augmented Prompt": metadata.get("augmented_prompt"),
                    "Type": metadata.get("type"),
                    "Segment ID": metadata.get("segment_id"),
                    "Document (Memory Content)": metadata.get(
                        "raw_content", data["documents"][i]
                    ),
                }
            )

        # Sort data by timestamp so newest entries appear first in the viewer
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


def inspect_database_cli():
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
                choice = int(
                    input("\\nEnter the number of the collection to inspect: ")
                )
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
