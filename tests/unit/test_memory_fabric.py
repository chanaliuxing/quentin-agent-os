import pytest
from unittest.mock import MagicMock, AsyncMock
from datetime import datetime
import asyncio # for async_sleep in mock

from quentin.memory.fabric import MemoryFabric
from quentin.memory.models import MemoryRecord, MemoryTier, MemoryQuery
from quentin.memory.store_sqlite import SqliteMemoryStore


@pytest.fixture
def mock_sqlite_memory_store():
    mock = AsyncMock(spec=SqliteMemoryStore)
    # The SqliteMemoryStore.__init__ calls init(), so we need to mock that too.
    # Or simply replace the store attribute after instantiation.
    mock.init = AsyncMock() # Mock the init method
    
    # Configure mock responses if necessary
    yield mock

@pytest.fixture
def memory_fabric(mock_sqlite_memory_store):
    # MemoryFabric's __init__ calls SqliteMemoryStore(db_path), then store.init().
    # We need to mock SqliteMemoryStore's constructor if we don't want it to create real DB.
    # Or, simpler: patch the SqliteMemoryStore class itself during the test, or replace the instance.
    
    # Let's replace the store attribute after instantiation for simplicity
    fabric = MemoryFabric(db_path=":memory:") # Pass a dummy, won't be used by mock
    fabric.store = mock_sqlite_memory_store # Inject the mock instance
    return fabric

@pytest.fixture(autouse=True)
def _clear_memory_recall_defaults_env(monkeypatch):
    monkeypatch.delenv("QUENTIN_MEMORY_RECALL_DEFAULTS_ENABLE", raising=False)
    monkeypatch.delenv("QUENTIN_MEMORY_RECALL_DEFAULTS_PATH", raising=False)

@pytest.mark.asyncio
async def test_remember_atomic(memory_fabric, mock_sqlite_memory_store):
    content = "Test content"
    source = "test_source"
    tier = MemoryTier.STS
    
    record = memory_fabric.remember_atomic(content=content, source=source, tier=tier)
    
    # Ensure MemoryFabric creates a MemoryRecord correctly
    assert isinstance(record, MemoryRecord)
    assert record.content == content
    assert record.source == source
    assert record.tier == tier
    
    # Ensure it calls store.add with the correct record
    mock_sqlite_memory_store.add.assert_called_once_with(record)


@pytest.mark.asyncio
async def test_recall(memory_fabric, mock_sqlite_memory_store):
    query = MemoryQuery(text="test query")
    expected_results = [
        MemoryRecord.new(tier=MemoryTier.STS, content="found", source="test")
    ]
    mock_sqlite_memory_store.search.return_value = expected_results
    
    results = memory_fabric.recall(query)
    
    mock_sqlite_memory_store.search.assert_called_once_with(query)
    assert results == expected_results

@pytest.mark.asyncio
async def test_promote_to_mts(memory_fabric, mock_sqlite_memory_store):
    record_ids = ["rec_id_1", "rec_id_2"]
    memory_fabric.promote_to_mts(record_ids) # Removed await
    
    assert mock_sqlite_memory_store.promote.call_count == len(record_ids)
    mock_sqlite_memory_store.promote.assert_any_call("rec_id_1", MemoryTier.MTS)
    mock_sqlite_memory_store.promote.assert_any_call("rec_id_2", MemoryTier.MTS)

@pytest.mark.asyncio
async def test_promote_to_lts(memory_fabric, mock_sqlite_memory_store):
    record_ids = ["rec_id_3"]
    memory_fabric.promote_to_lts(record_ids) # Removed await
    
    assert mock_sqlite_memory_store.promote.call_count == 1 
    mock_sqlite_memory_store.promote.assert_called_once_with("rec_id_3", MemoryTier.LTS)

@pytest.mark.asyncio
async def test_decay_records(memory_fabric, mock_sqlite_memory_store):
    record_ids = ["rec_id_4"]
    memory_fabric.decay_records(record_ids) # Removed await
    
    mock_sqlite_memory_store.mark_decayed.assert_called_once_with("rec_id_4")

# Note: Tier migration logic (based on age/access_count) is typically in SleepLoop
# The tests above verify that MemoryFabric correctly delegates to its store.
# Further tests for SqliteMemoryStore would verify the actual persistence and querying.
