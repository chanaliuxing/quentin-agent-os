from datetime import timedelta

from quentin.memory.fabric import MemoryFabric
from quentin.memory.models import MemoryRecord, MemoryTier
from quentin.memory.store_sqlite import SqliteMemoryStore
from quentin.utils.time import now_utc


def test_safe_forgetting_decays_old_low_value_sts(tmp_path) -> None:
    store = SqliteMemoryStore(tmp_path / "mem.db")
    store.init()
    fabric = MemoryFabric(store=store, trace_recorder=None)

    rec = MemoryRecord.new(
        tier=MemoryTier.STS,
        content="old low value",
        source="test",
        importance=0.0,
    )
    rec.created_at = now_utc() - timedelta(hours=200)
    rec.updated_at = rec.created_at
    store.add(rec)

    report = fabric.run_safe_forgetting()
    assert report["sts_decayed"] >= 1
    assert store.get(rec.id) is None

