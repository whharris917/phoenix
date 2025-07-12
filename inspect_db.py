import chromadb
import os
import pandas as pd

# Define the path to the ChromaDB database directory
# This should match the path used in memory_manager.py
# Assumes you are running this script from the project's root directory.
CHROMA_DB_PATH = os.path.join(os.getcwd(), '.sandbox', 'chroma_db')

def inspect_database():
    """Connects to the ChromaDB and prints its contents in a readable format."""
    print(f"--- ChromaDB Inspector ---")
    print(f"Connecting to database at: {CHROMA_DB_PATH}\n")

    if not os.path.exists(CHROMA_DB_PATH):
        print("Error: ChromaDB directory not found.")
        print("Please ensure the main application has been run at least once to create the database.")
        return

    try:
        # Initialize the client
        client = chromadb.PersistentClient(path=CHROMA_DB_PATH)

        # List all collections (sessions)
        collections = client.list_collections()
        if not collections:
            print("No collections (sessions) found in the database.")
            return

        print("Available Collections (Sessions):")
        for i, collection in enumerate(collections):
            print(f"  {i+1}. {collection.name} (Documents: {collection.count()})")
        
        # Prompt the user to select a collection
        while True:
            try:
                choice = int(input("\nEnter the number of the collection to inspect: "))
                if 1 <= choice <= len(collections):
                    selected_collection = collections[choice-1]
                    break
                else:
                    print("Invalid choice. Please try again.")
            except ValueError:
                print("Invalid input. Please enter a number.")

        # Retrieve all data from the selected collection
        print(f"\n--- Inspecting Collection: {selected_collection.name} ---")
        data = selected_collection.get(include=["metadatas", "documents"])
        
        if not data or not data['ids']:
            print("This collection is empty.")
            return

        # Use pandas for pretty printing
        df = pd.DataFrame({
            'ID': data['ids'],
            'Role': [meta.get('role', 'N/A') if meta else 'N/A' for meta in data['metadatas']],
            'Document (Memory Content)': data['documents']
        })
        pd.set_option('display.max_rows', None)
        pd.set_option('display.max_colwidth', None)
        pd.set_option('display.width', 1000)

        print(df)

    except Exception as e:
        print(f"\nAn error occurred: {e}")
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    inspect_database()
