import chromadb
import os
import fnmatch

SANDBOX_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".sandbox")
CHROMA_DB_PATH = os.path.join(SANDBOX_DIR, "chroma_db")


def manage_collections():
    """
    Connects to ChromaDB, lists collections, and deletes collections matching a user-provided pattern.
    """
    if not os.path.exists(CHROMA_DB_PATH):
        print(f"ChromaDB path not found at: {CHROMA_DB_PATH}")
        print(
            "Please ensure the agent has been run at least once to create the database."
        )
        return

    try:
        client = chromadb.PersistentClient(path=CHROMA_DB_PATH)
        collections = client.list_collections()

        if not collections:
            print("No collections found in the ChromaDB database.")
            return

        collection_names = [c.name for c in collections]

        print("Available collections:")
        for i, name in enumerate(collection_names):
            print(f"  {i + 1}. {name}")

        print(
            "\nPlease enter the name or a wildcard pattern (e.g., 'session_*') of the collection(s) you wish to delete."
        )
        pattern = input("> ")

        collections_to_delete = [
            name for name in collection_names if fnmatch.fnmatch(name, pattern)
        ]

        if not collections_to_delete:
            print(f"No collections found matching the pattern: {pattern}")
            return

        print("\nThe following collections will be deleted:")
        for name in collections_to_delete:
            print(f"  - {name}")

        print(
            f"\nAre you sure you want to permanently delete these {len(collections_to_delete)} collections? (yes/no)"
        )
        confirmation = input("> ").lower()

        if confirmation == "yes":
            for name in collections_to_delete:
                try:
                    client.delete_collection(name=name)
                    print(f"Successfully deleted collection: {name}")
                except Exception as e:
                    print(f"Error deleting collection {name}: {e}")
            print("\nDeletion process complete.")
        else:
            print("Deletion cancelled.")

    except Exception as e:
        print(f"An error occurred: {e}")


if __name__ == "__main__":
    manage_collections()
