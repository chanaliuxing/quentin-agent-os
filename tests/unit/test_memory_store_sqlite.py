import os
from datetime import datetime
from quentin.memory.store_sqlite import SqliteMemoryStore
from quentin.memory.models import MemoryRecord, MemoryTier, MemoryQuery


def test_vector_search_prefers_closest():
    store = SqliteMemoryStore(":memory:")
    store.init()

    rec_a = MemoryRecord.new(
        tier=MemoryTier.STS,
        content="vector A",
        source="test",
        vector=[1.0, 0.0],
    )
    rec_b = MemoryRecord.new(
        tier=MemoryTier.STS,
        content="vector B",
        source="test",
        vector=[0.0, 1.0],
    )
    store.add(rec_a)
    store.add(rec_b)

    query = MemoryQuery(vector=[1.0, 0.0], top_k=1)
    results = store.search(query)

    assert len(results) == 1
    assert results[0].id == rec_a.id


def test_vector_search_uses_two_phase_strategy_by_default():
    store = SqliteMemoryStore(":memory:")
    assert getattr(store, "_vector_fetch_strategy", "") == "two_phase"


def test_vector_search_strategy_can_be_disabled(monkeypatch):
    monkeypatch.setenv("QUENTIN_MEMORY_VECTOR_TWO_PHASE_FETCH", "0")
    store = SqliteMemoryStore(":memory:")
    assert getattr(store, "_vector_fetch_strategy", "") == "single_phase"

    store.init()
    rec_a = MemoryRecord.new(
        tier=MemoryTier.STS,
        content="single phase A",
        source="test",
        vector=[1.0, 0.0],
    )
    rec_b = MemoryRecord.new(
        tier=MemoryTier.STS,
        content="single phase B",
        source="test",
        vector=[0.0, 1.0],
    )
    store.add(rec_a)
    store.add(rec_b)
    out = store.search(MemoryQuery(vector=[1.0, 0.0], top_k=1))
    assert out
    assert out[0].id == rec_a.id


def test_add_recovers_when_memories_table_missing(tmp_path):
    db_path = tmp_path / "mem.db"
    store = SqliteMemoryStore(db_path)
    store.init()

    store.conn.execute("DROP TABLE memories")
    store.conn.commit()

    rec = MemoryRecord.new(
        tier=MemoryTier.STS,
        content="recover schema",
        source="test",
    )
    store.add(rec)

    got = store.get(rec.id)
    assert got is not None
    assert got.content == "recover schema"


def test_reindex_indexes_atomic_success_keeps_data(tmp_path):
    db_path = tmp_path / "mem.db"
    store = SqliteMemoryStore(db_path)
    store.init()
    rec = MemoryRecord.new(tier=MemoryTier.STS, content="atomic ok", source="test")
    store.add(rec)

    result = store.reindex_indexes()
    assert result["status"] == "ok"
    got = store.get(rec.id)
    assert got is not None
    assert got.content == "atomic ok"


def test_reindex_indexes_atomic_failure_preserves_original(tmp_path, monkeypatch):
    db_path = tmp_path / "mem.db"
    store = SqliteMemoryStore(db_path)
    store.init()
    rec = MemoryRecord.new(tier=MemoryTier.STS, content="atomic rollback", source="test")
    store.add(rec)

    def _boom(_conn):
        raise RuntimeError("reindex failed")

    monkeypatch.setattr(store, "_run_reindex_on_connection", _boom)
    result = store.reindex_indexes()
    assert result["status"] == "failed"

    # Original DB remains readable and unchanged.
    got = store.get(rec.id)
    assert got is not None
    assert got.content == "atomic rollback"


def test_text_search_like_token_and_matches_reordered_query() -> None:
    store = SqliteMemoryStore(":memory:")
    store.init()
    rec = MemoryRecord.new(
        tier=MemoryTier.STS,
        content="incident in module auth root-cause signature 7",
        source="test",
    )
    store.add(rec)

    # Query words are reordered compared to content; token-AND LIKE should still match.
    q = MemoryQuery(text="auth module incident signature 7", top_k=5, mode="text_only")
    out = store.search(q)
    assert out
    assert out[0].id == rec.id


def test_text_search_keeps_numeric_tokens_for_case_id_disambiguation() -> None:
    store = SqliteMemoryStore(":memory:")
    store.init()
    rec1 = MemoryRecord.new(
        tier=MemoryTier.STS,
        content="auth incident case-id 7 signature",
        source="test",
    )
    rec2 = MemoryRecord.new(
        tier=MemoryTier.STS,
        content="auth incident case-id 8 signature",
        source="test",
    )
    store.add(rec1)
    store.add(rec2)

    out = store.search(MemoryQuery(text="auth case-id 7 signature", top_k=5, mode="text_only"))
    ids = {r.id for r in out}
    assert rec1.id in ids
    assert rec2.id not in ids


def test_text_search_numeric_token_boundary_avoids_partial_substring_hits() -> None:
    store = SqliteMemoryStore(":memory:")
    store.init()
    hit = MemoryRecord.new(
        tier=MemoryTier.STS,
        content="auth incident case-id 10 signature",
        source="test",
    )
    noise = MemoryRecord.new(
        tier=MemoryTier.STS,
        content="auth incident case-id 210 signature",
        source="test",
    )
    store.add(hit)
    store.add(noise)

    out = store.search(MemoryQuery(text="auth case-id 10 signature", top_k=10, mode="text_only"))
    ids = {r.id for r in out}
    assert hit.id in ids
    assert noise.id not in ids


def test_touch_access_many_increments_access_count() -> None:
    store = SqliteMemoryStore(":memory:")
    store.init()
    rec = MemoryRecord.new(
        tier=MemoryTier.STS,
        content="touch access",
        source="test",
    )
    store.add(rec)
    before = store.get(rec.id)
    assert before is not None
    assert before.access_count == 0

    store.touch_access_many([rec.id], datetime.now())
    after = store.get(rec.id)
    assert after is not None
    assert after.access_count == 1
    assert after.last_accessed_at is not None
