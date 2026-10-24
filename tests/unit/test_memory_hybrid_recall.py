from quentin.memory.fabric import MemoryFabric
from quentin.memory.models import MemoryRecord, MemoryTier, MemoryQuery


def _add_record(fabric: MemoryFabric, content: str, vector: list[float]) -> MemoryRecord:
    rec = MemoryRecord.new(
        tier=MemoryTier.STS,
        content=content,
        source="test",
        importance=0.5,
        vector=vector,
    )
    fabric.store.add(rec)
    return rec


def test_text_only_ignores_vector() -> None:
    fabric = MemoryFabric(db_path=":memory:")
    rec_text = _add_record(fabric, "error code E123", [1.0, 0.0])
    rec_vec = _add_record(fabric, "network timeout", [0.0, 1.0])

    query = MemoryQuery(text="E123", vector=[0.0, 1.0], mode="text_only", top_k=10)
    results = fabric.recall(query)
    ids = [r.id for r in results]

    assert rec_text.id in ids
    assert rec_vec.id not in ids


def test_vector_only_ignores_text() -> None:
    fabric = MemoryFabric(db_path=":memory:")
    rec_text = _add_record(fabric, "error code E123", [1.0, 0.0])
    rec_vec = _add_record(fabric, "network timeout", [0.0, 1.0])

    query = MemoryQuery(text="E123", vector=[0.0, 1.0], mode="vector_only", top_k=5)
    results = fabric.recall(query)

    assert results
    assert results[0].id == rec_vec.id
    assert results[0].id != rec_text.id


def test_hybrid_includes_text_and_vector_hits() -> None:
    fabric = MemoryFabric(db_path=":memory:")
    rec_text = _add_record(fabric, "E123 code path", [1.0, 0.0])
    rec_vec = _add_record(fabric, "network timeout", [0.0, 1.0])
    rec_both = _add_record(fabric, "E123 timeout", [0.6, 0.4])

    query = MemoryQuery(
        text="E123",
        vector=[0.0, 1.0],
        mode="hybrid",
        top_k=3,
        k_text=2,
        k_vec=2,
        alpha=0.5,
    )
    results = fabric.recall(query)
    ids = {r.id for r in results}

    assert rec_text.id in ids
    assert rec_vec.id in ids
    assert rec_both.id in ids


def test_hybrid_keyword_anchor_preserves_exact_text_hit(monkeypatch) -> None:
    monkeypatch.setenv("QUENTIN_MEMORY_HYBRID_KEYWORD_ANCHOR_TOPN", "1")
    fabric = MemoryFabric(db_path=":memory:")
    rec_text = _add_record(fabric, "TOKEN_XYZ", [1.0, 0.0])
    rec_vec = _add_record(fabric, "semantic near", [0.0, 1.0])
    # Add extra vector-near records to make vector results dominate head ranks.
    for i in range(8):
        _add_record(fabric, f"noise-{i}", [0.0, 1.0])

    query = MemoryQuery(
        text="TOKEN_XYZ",
        vector=[0.0, 1.0],
        mode="hybrid",
        top_k=2,
        k_text=1,
        k_vec=10,
        alpha=0.5,
    )
    results = fabric.recall(query)
    ids = {r.id for r in results}
    assert rec_text.id in ids
    assert len(ids) == 2
    assert any(r.id != rec_text.id for r in results)
    assert results[0].id == rec_text.id


def test_score_text_splits_nonword_tokens() -> None:
    fabric = MemoryFabric(db_path=":memory:")
    s = fabric._score_text("auth case-id 7 signature", "incident auth case id 7 signature")
    assert s > 0.5


def test_hybrid_fast_vector_seed_path_preserves_quality(monkeypatch) -> None:
    monkeypatch.setenv("QUENTIN_MEMORY_HYBRID_FAST_VECTOR_SEED", "1")
    monkeypatch.setenv("QUENTIN_MEMORY_HYBRID_FAST_FALLBACK_ENABLE", "0")
    monkeypatch.setenv("QUENTIN_MEMORY_HYBRID_VECTOR_SEED_TOPK", "20")

    fabric = MemoryFabric(db_path=":memory:")
    rec_text = _add_record(fabric, "incident auth case-id 7 signature", [0.0, 1.0])
    _noise = _add_record(fabric, "random unrelated text", [0.0, 1.0])

    query = MemoryQuery(
        text="auth case-id 7 signature",
        vector=[0.0, 1.0],
        mode="hybrid",
        top_k=5,
        k_text=5,
        k_vec=5,
    )
    results = fabric.recall(query)
    ids = {r.id for r in results}
    assert rec_text.id in ids


def test_hybrid_structured_query_forces_fallback_when_fast_seed_misses_exact_token(monkeypatch) -> None:
    monkeypatch.setenv("QUENTIN_MEMORY_HYBRID_FAST_VECTOR_SEED", "1")
    monkeypatch.setenv("QUENTIN_MEMORY_HYBRID_FAST_FALLBACK_ENABLE", "1")
    monkeypatch.setenv("QUENTIN_MEMORY_HYBRID_FAST_FALLBACK_MIN_HITS", "1")
    monkeypatch.setenv("QUENTIN_MEMORY_HYBRID_VECTOR_SEED_TOPK", "10")
    monkeypatch.setenv("QUENTIN_MEMORY_HYBRID_KEYWORD_ANCHOR_TOPN", "1")

    fabric = MemoryFabric(db_path=":memory:")
    # Exact structured token only appears in this record.
    target = _add_record(fabric, "[CODE:E4242] critical failure", [1.0, 0.0])
    # Vector-near distractors that can produce weak lexical overlaps via "code/error" wording.
    for i in range(20):
        _add_record(fabric, f"generic code error noise-{i}", [0.0, 1.0])

    out = fabric.recall(
        MemoryQuery(
            text="[CODE:E4242]",
            vector=[0.0, 1.0],
            mode="hybrid",
            top_k=3,
            k_text=3,
            k_vec=5,
        )
    )
    ids = {r.id for r in out}
    assert target.id in ids


def test_recall_writeback_can_be_disabled(monkeypatch) -> None:
    monkeypatch.setenv("QUENTIN_MEMORY_RECALL_WRITEBACK_ENABLE", "0")
    fabric = MemoryFabric(db_path=":memory:")
    rec = _add_record(fabric, "writeback disabled sample", [1.0, 0.0])
    out = fabric.recall(MemoryQuery(text="writeback", mode="text_only", top_k=5))
    assert out
    got = fabric.store.get(rec.id)
    assert got is not None
    assert got.access_count == 0


def test_text_query_prefers_fts_with_like_fallback(monkeypatch) -> None:
    class _StubStore:
        def __init__(self) -> None:
            self.calls = []
            self._fts_enabled = True

        def search(self, q):
            self.calls.append(str(getattr(q, "text_mode", "") or ""))
            if len(self.calls) == 1:
                return []
            return [MemoryRecord.new(tier=MemoryTier.STS, content="hit", source="t")]

        def update(self, _rec):
            return None

    stub = _StubStore()
    fabric = MemoryFabric(db_path=":memory:")
    fabric.store = stub  # type: ignore[assignment]
    monkeypatch.setattr(fabric, "_estimated_total_records", lambda: 10000)
    q = MemoryQuery(text="needle", mode="text_only", top_k=3)
    out = fabric.recall(q)
    assert out
    assert stub.calls[:2] == ["fts", "like"]


def test_online_active_window_sets_since_when_large(monkeypatch) -> None:
    fabric = MemoryFabric(db_path=":memory:")
    monkeypatch.setattr(fabric, "_estimated_total_records", lambda: 500000)
    monkeypatch.setenv("QUENTIN_MEMORY_ONLINE_ACTIVE_WINDOW_ENABLE", "1")
    monkeypatch.setenv("QUENTIN_MEMORY_ONLINE_OFFLINE_THRESHOLD", "300000")
    monkeypatch.setenv("QUENTIN_MEMORY_ONLINE_ACTIVE_WINDOW_DAYS", "30")
    q = MemoryQuery(text="x", mode="hybrid", top_k=5)
    q2 = fabric._apply_online_active_window(q)
    assert q2.since is not None
