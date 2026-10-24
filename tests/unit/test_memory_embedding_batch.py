from __future__ import annotations

from pathlib import Path

import httpx

from quentin.memory.embedding_batch import (
    BatchEmbeddingConfig,
    BatchEmbeddingManager,
    BatchJobStore,
    EmbeddingCache,
    NonRetryableBatchError,
    ProviderDisabledBatchError,
    RetryableBatchError,
    build_embedding_fingerprint,
    resolve_batch_concurrency,
)
from quentin.memory.fabric import MemoryFabric
from quentin.memory.models import MemoryTier


class _DummyEmbeddingClient:
    def __init__(self) -> None:
        self.calls = 0

    def embed_text(self, text: str):
        self.calls += 1
        size = float(len(text))
        return [size, size + 1.0]

    @property
    def dim(self) -> int:
        return 2


def test_batch_manager_dedup_and_cache(tmp_path: Path) -> None:
    cache = EmbeddingCache(tmp_path / "embed_cache.sqlite")
    client = _DummyEmbeddingClient()
    manager = BatchEmbeddingManager(
        embedding_client=client,
        config=BatchEmbeddingConfig(provider="dummy", model="dummy", provider_key="k1"),
        cache=cache,
    )

    vectors = manager.embed_texts(["alpha", "alpha", "beta"])
    assert len(vectors) == 3
    assert vectors[0] == vectors[1]
    assert client.calls == 2

    vectors_again = manager.embed_texts(["alpha", "beta"])
    assert vectors_again[0] == vectors[0]
    assert vectors_again[1] == vectors[2]
    assert client.calls == 2

    fp = build_embedding_fingerprint(provider="dummy", model="dummy::k1", text="alpha")
    assert cache.get(fp) == vectors[0]


def test_batch_manager_provider_key_partitions_cache(tmp_path: Path) -> None:
    cache = EmbeddingCache(tmp_path / "embed_cache.sqlite")
    client = _DummyEmbeddingClient()
    manager_a = BatchEmbeddingManager(
        embedding_client=client,
        config=BatchEmbeddingConfig(provider="dummy", model="dummy", provider_key="k1"),
        cache=cache,
    )
    manager_b = BatchEmbeddingManager(
        embedding_client=client,
        config=BatchEmbeddingConfig(provider="dummy", model="dummy", provider_key="k2"),
        cache=cache,
    )

    manager_a.embed_texts(["same"])
    manager_b.embed_texts(["same"])
    assert client.calls == 2


def test_openai_batch_failure_disables_batch_and_fallback(tmp_path: Path) -> None:
    cache = EmbeddingCache(tmp_path / "embed_cache.sqlite")
    client = _DummyEmbeddingClient()
    manager = BatchEmbeddingManager(
        embedding_client=client,
        config=BatchEmbeddingConfig(
            provider="openai",
            model="text-embedding-3-small",
            provider_key="k1",
            openai_api_key="sk-test",
            batch_failure_limit=2,
        ),
        cache=cache,
    )

    manager._embed_openai_batch = lambda **_: (_ for _ in ()).throw(RuntimeError("boom"))  # type: ignore[attr-defined]
    manager.embed_texts(["a"])
    manager.embed_texts(["b"])
    assert client.calls == 2
    assert manager._batch_enabled is False  # type: ignore[attr-defined]
    status = manager.status()
    assert int(status["fallback_calls_total"]) >= 2


def test_openai_async_parse_output_keeps_input_order(tmp_path: Path) -> None:
    cache = EmbeddingCache(tmp_path / "embed_cache.sqlite")
    client = _DummyEmbeddingClient()
    manager = BatchEmbeddingManager(
        embedding_client=client,
        config=BatchEmbeddingConfig(provider="openai", model="m", provider_key="k"),
        cache=cache,
    )
    lines = [
        {"custom_id": "req_1", "response": {"body": {"data": [{"embedding": [2.0, 2.0]}]}}},
        {"custom_id": "req_0", "response": {"body": {"data": [{"embedding": [1.0, 1.0]}]}}},
    ]
    vectors = manager._openai_async_parse_output(lines=lines, texts=["a", "b"])  # type: ignore[attr-defined]
    assert vectors == [[1.0, 1.0], [2.0, 2.0]]


def test_openai_async_parse_output_missing_item_raises(tmp_path: Path) -> None:
    cache = EmbeddingCache(tmp_path / "embed_cache.sqlite")
    client = _DummyEmbeddingClient()
    manager = BatchEmbeddingManager(
        embedding_client=client,
        config=BatchEmbeddingConfig(provider="openai", model="m", provider_key="k"),
        cache=cache,
    )
    lines = [{"custom_id": "req_0", "response": {"body": {"data": [{"embedding": [1.0, 1.0]}]}}}]
    try:
        manager._openai_async_parse_output(lines=lines, texts=["a", "b"])  # type: ignore[attr-defined]
        raise AssertionError("expected RuntimeError")
    except RuntimeError as e:
        assert "missing items" in str(e).lower()


def test_gemini_async_parse_output_keeps_input_order(tmp_path: Path) -> None:
    cache = EmbeddingCache(tmp_path / "embed_cache.sqlite")
    client = _DummyEmbeddingClient()
    manager = BatchEmbeddingManager(
        embedding_client=client,
        config=BatchEmbeddingConfig(provider="gemini", model="m", provider_key="k"),
        cache=cache,
    )
    lines = [
        {"key": "req_1", "response": {"embedding": {"values": [2.0, 2.0]}}},
        {"key": "req_0", "embedding": {"values": [1.0, 1.0]}},
    ]
    vectors = manager._gemini_async_parse_output(lines=lines, texts=["a", "b"], batch_name="b1")  # type: ignore[attr-defined]
    assert vectors == [[1.0, 1.0], [2.0, 2.0]]


def test_gemini_async_parse_output_missing_item_raises(tmp_path: Path) -> None:
    cache = EmbeddingCache(tmp_path / "embed_cache.sqlite")
    client = _DummyEmbeddingClient()
    manager = BatchEmbeddingManager(
        embedding_client=client,
        config=BatchEmbeddingConfig(provider="gemini", model="m", provider_key="k"),
        cache=cache,
    )
    lines = [{"key": "req_0", "embedding": {"values": [1.0, 1.0]}}]
    try:
        manager._gemini_async_parse_output(lines=lines, texts=["a", "b"], batch_name="b1")  # type: ignore[attr-defined]
        raise AssertionError("expected RuntimeError")
    except RuntimeError as e:
        assert "missing items" in str(e).lower()


def test_memory_fabric_remember_many_atomic(tmp_path: Path, monkeypatch) -> None:
    client = _DummyEmbeddingClient()
    monkeypatch.setenv("QUENTIN_MEMORY_EMBED_CACHE_PATH", str(tmp_path / "memory_embed_cache.sqlite"))
    fabric = MemoryFabric(db_path=":memory:", embedding_client=client)

    recs = fabric.remember_many_atomic(
        [
            {"content": "same text", "source": "t", "tier": MemoryTier.STS},
            {"content": "same text", "source": "t", "tier": MemoryTier.STS},
            {"content": "new text", "source": "t", "tier": MemoryTier.STS},
        ]
    )
    assert len(recs) == 3
    assert recs[0].vector == recs[1].vector
    assert all(r.vector for r in recs)
    assert client.calls == 2


def test_memory_fabric_stats_contains_batch_and_tiers(tmp_path: Path, monkeypatch) -> None:
    client = _DummyEmbeddingClient()
    monkeypatch.setenv("QUENTIN_MEMORY_EMBED_CACHE_PATH", str(tmp_path / "memory_embed_cache.sqlite"))
    fabric = MemoryFabric(db_path=":memory:", embedding_client=client)
    fabric.remember_atomic(content="s1", source="t", tier=MemoryTier.STS)
    fabric.remember_atomic(content="m1", source="t", tier=MemoryTier.MTS)

    stats = fabric.stats()
    assert "batch" in stats
    assert "vector" in stats
    assert "tier_counts" in stats
    assert stats["total_records"] >= 2
    assert stats["tier_counts"]["short_term"] >= 1
    assert stats["tier_counts"]["mid_term"] >= 1
    assert str(stats["vector"]["backend"]) in ("sqlite_vec", "client_scan")
    assert str(stats["vector"]["math_backend"]) in ("numpy", "python", "unknown")
    assert str(stats["vector"]["fetch_strategy"]) in ("two_phase", "single_phase", "unknown")


def test_resolve_batch_concurrency_by_tier() -> None:
    assert resolve_batch_concurrency(account_tier=1, configured=0) == 2
    assert resolve_batch_concurrency(account_tier=3, configured=0) == 8
    assert resolve_batch_concurrency(account_tier=5, configured=0) == 100
    assert resolve_batch_concurrency(account_tier=5, configured=10) == 100
    assert resolve_batch_concurrency(account_tier=2, configured=20) == 20


def test_batch_status_contains_tier_and_concurrency(tmp_path: Path) -> None:
    cache = EmbeddingCache(tmp_path / "embed_cache.sqlite")
    client = _DummyEmbeddingClient()
    manager = BatchEmbeddingManager(
        embedding_client=client,
        config=BatchEmbeddingConfig(
            provider="openai",
            model="m",
            provider_key="k",
            account_tier=5,
            batch_concurrency=0,
        ),
        cache=cache,
    )
    status = manager.status()
    assert status["account_tier"] == 5
    assert status["batch_concurrency"] == 100
    assert int(status["retry_max_attempts"]) >= 1


def test_openai_async_resume_existing_job(tmp_path: Path, monkeypatch) -> None:
    cache = EmbeddingCache(tmp_path / "embed_cache.sqlite")
    client = _DummyEmbeddingClient()
    job_path = tmp_path / "batch_jobs.sqlite"
    manager = BatchEmbeddingManager(
        embedding_client=client,
        config=BatchEmbeddingConfig(
            provider="openai",
            model="m",
            provider_key="k",
            openai_async_batch_enabled=True,
            openai_api_key="sk",
            job_store_path=str(job_path),
        ),
        cache=cache,
    )
    fp = "fp-openai-1"
    assert isinstance(manager.job_store, BatchJobStore)
    manager.job_store.upsert(
        fingerprint=fp,
        provider="openai",
        model="m",
        batch_id="batch_old",
        status="submitted",
    )

    monkeypatch.setattr(
        "quentin.memory.embedding_batch.wait_batch_output_file",
        lambda **kwargs: "out_file_1",
    )

    batch_id, out_id = manager._openai_async_submit_and_wait(  # type: ignore[attr-defined]
        client=object(),  # not used by monkeypatched wait func
        base_url="https://api.openai.com/v1",
        model="m",
        headers={"Authorization": "Bearer sk"},
        texts=["hello"],
        batch_fingerprint=fp,
    )
    assert batch_id == "batch_old"
    assert out_id == "out_file_1"
    row = manager.job_store.get(fp)
    assert row is not None
    assert row["status"] == "completed"
    status = manager.status()
    assert int(status["resumed_jobs_total"]) >= 1


def test_retry_counter_increments(tmp_path: Path) -> None:
    cache = EmbeddingCache(tmp_path / "embed_cache.sqlite")
    client = _DummyEmbeddingClient()
    manager = BatchEmbeddingManager(
        embedding_client=client,
        config=BatchEmbeddingConfig(provider="openai", model="m", provider_key="k"),
        cache=cache,
    )

    class _Resp:
        status_code = 200

    out = manager._retry_http_call(lambda: _Resp())  # type: ignore[attr-defined]
    assert out.status_code == 200
    status = manager.status()
    assert int(status["retry_attempts_total"]) >= 1


def test_retry_http_call_non_retryable_status_raises(tmp_path: Path) -> None:
    cache = EmbeddingCache(tmp_path / "embed_cache.sqlite")
    client = _DummyEmbeddingClient()
    manager = BatchEmbeddingManager(
        embedding_client=client,
        config=BatchEmbeddingConfig(provider="openai", model="m", provider_key="k"),
        cache=cache,
    )

    req = httpx.Request("POST", "https://api.openai.com/v1/embeddings")
    resp = httpx.Response(401, request=req)
    try:
        manager._retry_http_call(lambda: resp)  # type: ignore[attr-defined]
        raise AssertionError("expected NonRetryableBatchError")
    except NonRetryableBatchError:
        pass


def test_retry_http_call_transport_retryable_raises(tmp_path: Path) -> None:
    cache = EmbeddingCache(tmp_path / "embed_cache.sqlite")
    client = _DummyEmbeddingClient()
    manager = BatchEmbeddingManager(
        embedding_client=client,
        config=BatchEmbeddingConfig(provider="openai", model="m", provider_key="k", retry_max_attempts=1),
        cache=cache,
    )

    try:
        manager._retry_http_call(lambda: (_ for _ in ()).throw(httpx.TransportError("net")))  # type: ignore[attr-defined]
        raise AssertionError("expected RetryableBatchError")
    except RetryableBatchError:
        pass


def test_provider_disabled_error_disables_batch_immediately(tmp_path: Path) -> None:
    cache = EmbeddingCache(tmp_path / "embed_cache.sqlite")
    client = _DummyEmbeddingClient()
    manager = BatchEmbeddingManager(
        embedding_client=client,
        config=BatchEmbeddingConfig(
            provider="openai",
            model="text-embedding-3-small",
            provider_key="k1",
            openai_api_key="",
            batch_failure_limit=10,
        ),
        cache=cache,
    )
    manager._embed_openai_batch = lambda **_: (_ for _ in ()).throw(ProviderDisabledBatchError("auth"))  # type: ignore[attr-defined]
    manager.embed_texts(["a"])
    assert manager._batch_enabled is False  # type: ignore[attr-defined]
    status = manager.status()
    assert int(status["provider_disabled_total"]) >= 1
