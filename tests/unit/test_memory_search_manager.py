from __future__ import annotations

import time
import asyncio

from quentin.memory.fabric import MemoryFabric
from quentin.memory.models import MemoryQuery, MemoryTier, MemoryRecord
from quentin.memory.search_manager import ParallelSearchManager, SearchManagerConfig, SessionSearchSpec


class _DummyEmbeddingClient:
    def embed_text(self, text: str):
        n = float(len(text))
        return [n, n + 1.0]

    @property
    def dim(self) -> int:
        return 2


class _FakeFabric:
    def __init__(self, records):
        self._records = list(records)

    def recall(self, query, **kwargs):  # noqa: ANN001, ANN003
        _ = query
        _ = kwargs
        return list(self._records)


class _SlowFakeFabric:
    def recall(self, query, **kwargs):  # noqa: ANN001, ANN003
        _ = query
        _ = kwargs
        time.sleep(0.25)
        return []


class _ErrorFakeFabric:
    def recall(self, query, **kwargs):  # noqa: ANN001, ANN003
        _ = query
        _ = kwargs
        raise RuntimeError("boom")


def test_parallel_search_manager_rrf_dedupes_shared_records() -> None:
    a = MemoryRecord.new(tier=MemoryTier.STS, content="a", source="session_delta:s1")
    b = MemoryRecord.new(tier=MemoryTier.STS, content="b", source="session_delta:s1")
    c = MemoryRecord.new(tier=MemoryTier.STS, content="c", source="session_delta:s2")
    c.id = a.id  # shared record id across lists, should dedupe/fuse score
    d = MemoryRecord.new(tier=MemoryTier.STS, content="d", source="session_delta:s2")
    fake = _FakeFabric([a, b, c, d])
    mgr = ParallelSearchManager(max_workers=2)

    result = mgr.search_across_sessions(
        memory_fabric=fake,
        base_query=MemoryQuery(text="x", top_k=3, mode="text_only"),
        session_specs=[
            SessionSearchSpec(session_id="s1", source_prefixes=["session_delta:s1"]),
            SessionSearchSpec(session_id="s2", source_prefixes=["session_delta:s2"]),
        ],
        top_k=3,
    )

    fused = result["records"]
    assert fused
    assert len({r.id for r in fused}) == len(fused)
    assert result["total_sessions"] == 2
    assert result["session_hits"]["s1"] >= 1
    assert result["session_hits"]["s2"] >= 1


def test_parallel_search_manager_schedules_by_priority_then_weight() -> None:
    fake = _FakeFabric([])
    mgr = ParallelSearchManager(max_workers=2)
    result = mgr.search_across_sessions(
        memory_fabric=fake,
        base_query=MemoryQuery(text="x", top_k=3, mode="text_only"),
        session_specs=[
            SessionSearchSpec(session_id="low", source_prefixes=[], weight=10, priority=0),
            SessionSearchSpec(session_id="high2", source_prefixes=[], weight=2, priority=5),
            SessionSearchSpec(session_id="high1", source_prefixes=[], weight=1, priority=5),
        ],
    )
    assert result["scheduled_sessions"] == ["high2", "high1", "low"]


def test_parallel_search_manager_rerank_source_prior() -> None:
    a = MemoryRecord.new(tier=MemoryTier.STS, content="a", source="memory_file:/x")
    b = MemoryRecord.new(tier=MemoryTier.STS, content="b", source="session_delta:s1")
    fake = _FakeFabric([a, b])
    mgr = ParallelSearchManager(
        config=SearchManagerConfig(
            max_workers=1,
            per_session_timeout_s=1.0,
            rerank_enabled=True,
            source_priors={"session_delta:": 1.0, "memory_file:": 0.0},
            domain_match_bonus=0.0,
            rerank_time_half_life_hours=9999.0,
        )
    )
    result = mgr.search_across_sessions(
        memory_fabric=fake,
        base_query=MemoryQuery(text="x", top_k=2, mode="text_only"),
        session_specs=[SessionSearchSpec(session_id="s", source_prefixes=[])],
        top_k=2,
    )
    assert result["records"]
    assert str(result["records"][0].source).startswith("session_delta:")
    assert result["rerank_applied"] is True


def test_parallel_search_manager_timeout_and_error_isolated() -> None:
    timeout_mgr = ParallelSearchManager(
        config=SearchManagerConfig(max_workers=2, per_session_timeout_s=0.1)
    )
    timeout_res = timeout_mgr.search_across_sessions(
        memory_fabric=_SlowFakeFabric(),
        base_query=MemoryQuery(text="x", top_k=3, mode="text_only"),
        session_specs=[
            SessionSearchSpec(session_id="s1", source_prefixes=[]),
            SessionSearchSpec(session_id="s2", source_prefixes=[]),
        ],
        top_k=3,
    )
    assert "s1" in timeout_res["timed_out_sessions"] or "s2" in timeout_res["timed_out_sessions"]
    assert timeout_res["errors"]

    err_mgr = ParallelSearchManager(
        config=SearchManagerConfig(max_workers=2, per_session_timeout_s=0.5)
    )
    err_res = err_mgr.search_across_sessions(
        memory_fabric=_ErrorFakeFabric(),
        base_query=MemoryQuery(text="x", top_k=3, mode="text_only"),
        session_specs=[SessionSearchSpec(session_id="s1", source_prefixes=[])],
        top_k=3,
    )
    assert "s1" in err_res["errors"]
    assert err_res["by_session"]["s1"] == []


def test_memory_fabric_recall_across_sessions_wrapper(tmp_path, monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.setenv("QUENTIN_MEMORY_EMBED_CACHE_PATH", str(tmp_path / "memory_embed_cache.sqlite"))
    fabric = MemoryFabric(repo_root=tmp_path, db_path=":memory:", embedding_client=_DummyEmbeddingClient())
    fabric.remember_atomic(content="alpha", source="session_delta:s1", tier=MemoryTier.STS)
    fabric.remember_atomic(content="beta", source="session_delta:s2", tier=MemoryTier.STS)
    fabric.remember_atomic(content="gamma", source="session_delta:s3", tier=MemoryTier.STS)

    result = fabric.recall_across_sessions(
        query=MemoryQuery(text="a", mode="text_only", top_k=10),
        session_sources={
            "s1": ["session_delta:s1"],
            "s2": ["session_delta:s2"],
        },
        top_k=5,
    )
    records = result["records"]
    assert records
    assert all(str(r.source).startswith(("session_delta:s1", "session_delta:s2")) for r in records)
    assert int(result["total_sessions"]) == 2
    assert isinstance(result.get("errors"), dict)
    stats = fabric.stats()
    assert "search" in stats
    assert int(stats["search"]["max_workers"]) >= 1


def test_memory_fabric_pre_search_hook_called_once_for_cross_session(tmp_path, monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.setenv("QUENTIN_MEMORY_EMBED_CACHE_PATH", str(tmp_path / "memory_embed_cache.sqlite"))
    fabric = MemoryFabric(repo_root=tmp_path, db_path=":memory:", embedding_client=_DummyEmbeddingClient())
    fabric.remember_atomic(content="alpha", source="session_delta:s1", tier=MemoryTier.STS)
    calls = {"n": 0}

    def _hook(q):  # noqa: ANN001
        _ = q
        calls["n"] += 1
        return {"status": "ok"}

    fabric.set_pre_search_sync_hook(_hook)
    fabric.recall_across_sessions(
        query=MemoryQuery(text="a", mode="text_only", top_k=5),
        session_sources={"s1": ["session_delta:s1"]},
    )
    assert calls["n"] == 1


def test_parallel_search_manager_async_cancel_and_timeout() -> None:
    async def _run() -> None:
        mgr = ParallelSearchManager(
            config=SearchManagerConfig(max_workers=2, per_session_timeout_s=0.5)
        )
        cancel_evt = asyncio.Event()
        cancel_evt.set()
        cancelled = await mgr.search_across_sessions_async(
            memory_fabric=_SlowFakeFabric(),
            base_query=MemoryQuery(text="x", top_k=3, mode="text_only"),
            session_specs=[SessionSearchSpec(session_id="s1", source_prefixes=[])],
            cancel_event=cancel_evt,
        )
        assert cancelled["cancelled"] is True
        assert "s1" in cancelled["cancelled_sessions"]

        timed = await mgr.search_across_sessions_async(
            memory_fabric=_SlowFakeFabric(),
            base_query=MemoryQuery(text="x", top_k=3, mode="text_only"),
            session_specs=[SessionSearchSpec(session_id="s1", source_prefixes=[])],
            overall_timeout_s=0.1,
        )
        assert timed["cancelled"] is True
        assert "s1" in timed["timed_out_sessions"]

    asyncio.run(_run())


def test_memory_fabric_recall_across_sessions_async_wrapper(tmp_path, monkeypatch) -> None:  # noqa: ANN001
    async def _run() -> None:
        monkeypatch.setenv("QUENTIN_MEMORY_EMBED_CACHE_PATH", str(tmp_path / "memory_embed_cache.sqlite"))
        fabric = MemoryFabric(repo_root=tmp_path, db_path=":memory:", embedding_client=_DummyEmbeddingClient())
        fabric.remember_atomic(content="alpha", source="session_delta:s1", tier=MemoryTier.STS)
        res = await fabric.recall_across_sessions_async(
            query=MemoryQuery(text="a", mode="text_only", top_k=10),
            session_sources={"s1": ["session_delta:s1"]},
            top_k=5,
        )
        assert res["records"]
        assert int(res["total_sessions"]) == 1
        assert isinstance(res.get("errors"), dict)

    asyncio.run(_run())


def test_parallel_search_manager_adaptive_session_cap() -> None:
    fake = _FakeFabric([])
    mgr = ParallelSearchManager(
        config=SearchManagerConfig(
            max_workers=2,
            per_session_timeout_s=1.0,
            adaptive_degrade_enabled=True,
            adaptive_session_cap_factor=2,
        )
    )
    specs = [SessionSearchSpec(session_id=f"s{i}", source_prefixes=[]) for i in range(8)]
    result = mgr.search_across_sessions(
        memory_fabric=fake,
        base_query=MemoryQuery(text="x", top_k=3, mode="text_only"),
        session_specs=specs,
    )
    assert len(result["scheduled_sessions"]) == 4
    assert bool(result["budget"]["adaptive_degrade_applied"]) is True


def test_parallel_search_manager_timeout_pressure_disables_rerank() -> None:
    mgr = ParallelSearchManager(
        config=SearchManagerConfig(
            max_workers=2,
            per_session_timeout_s=0.1,
            rerank_enabled=True,
            timeout_pressure_threshold=0.2,
        )
    )
    result = mgr.search_across_sessions(
        memory_fabric=_SlowFakeFabric(),
        base_query=MemoryQuery(text="x", top_k=3, mode="text_only"),
        session_specs=[
            SessionSearchSpec(session_id="s1", source_prefixes=[]),
            SessionSearchSpec(session_id="s2", source_prefixes=[]),
        ],
    )
    assert result["rerank_applied"] is False
    assert bool(result["budget"]["timeout_pressure"]) is True


def test_parallel_search_manager_timeout_threshold_zero_is_respected() -> None:
    mgr = ParallelSearchManager(
        config=SearchManagerConfig(
            max_workers=1,
            per_session_timeout_s=1.0,
            rerank_enabled=True,
            timeout_pressure_threshold=0.0,
        )
    )
    result = mgr.search_across_sessions(
        memory_fabric=_FakeFabric([]),
        base_query=MemoryQuery(text="x", top_k=3, mode="text_only"),
        session_specs=[SessionSearchSpec(session_id="s1", source_prefixes=[])],
    )
    assert bool(result["budget"]["timeout_pressure"]) is True
    assert result["rerank_applied"] is False
