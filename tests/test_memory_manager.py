import time
from memory_manager import ChromaDBStore
from data_models import MemoryRecord


def test_chromadb_store_add_record(mocker):
    """
    Tests that ChromaDBStore.add_record calls the underlying chromadb client
    with the correct, sanitized data.
    """
    # 1. ARRANGE:
    # Mock the entire chromadb library to prevent file system access
    mock_chroma_client = mocker.patch("memory_manager.chromadb.PersistentClient")

    # Create a mock collection object that our mock client will return
    mock_collection = mocker.MagicMock()
    mock_chroma_client.return_value.get_or_create_collection.return_value = mock_collection

    # Create a sample MemoryRecord to add
    test_record = MemoryRecord(role="user", timestamp=time.time(), document="Hello, world!", summary=None)  # This will be excluded

    # 2. ACT: Instantiate our class and call the method
    db_store = ChromaDBStore(collection_name="test-collection")
    db_store.add_record(test_record, str(test_record.id))

    # 3. ASSERT: Verify that the mock collection's `add` method was called exactly once
    mock_collection.add.assert_called_once()

    # Get the arguments that were passed to the mock `add` method
    call_args, call_kwargs = mock_collection.add.call_args

    # Check that the metadata dictionary passed to the DB does NOT contain 'None' values
    metadata_passed_to_db = call_kwargs["metadatas"][0]
    assert "summary" not in metadata_passed_to_db  # because it was None
    assert metadata_passed_to_db["role"] == "user"
