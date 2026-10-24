from __future__ import annotations

import os
import time
import uuid
from pathlib import Path

import psycopg
import pytest

from quentin.memory.fabric import MemoryFabric
from quentin.memory.models import MemoryQuery


def _pg_dsn_from_env_or_default() -> str:
    dsn = (os.getenv("PG_DSN") or "").strip()
    if dsn:
        return dsn
    host = (os.getenv("PG_HOST") or "127.0.0.1").strip()
    port = (os.getenv("PG_PORT") or "55432").strip()
    user = (os.getenv("PG_USER") or "postgres").strip()
    password = os.getenv("PG_PASSWORD", "postgres")
    db = (os.getenv("PG_DB") or "quentin_memory").strip()
    return f"postgresql://{user}:{password}@{host}:{port}/{db}"


def _pg_ready(dsn: str) -> bool:
    try:
        conn = psycopg.connect(dsn, connect_timeout=2)
        try:
            row = conn.execute("SELECT 1").fetchone()
            return bool(row)
        finally:
            conn.close()
    except Exception:
        return False


def _qdrant_ready(url: str) -> bool:
    try:
        import requests

        r = requests.get(f"{url.rstrip('/')}/readyz", timeout=1.0)
        return r.status_code == 200
    except Exception:
        return False


def test_champion_store_vector_recall_e2e_when_qdrant_ready(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    dsn = _pg_dsn_from_env_or_default()
    qdrant_url = (os.getenv("QDRANT_URL") or "http://127.0.0.1:6333").strip()
    if not _pg_ready(dsn):
        pytest.skip("Postgres not ready for champion e2e test.")
    if not _qdrant_ready(qdrant_url):
        pytest.skip("Qdrant not ready for champion e2e test.")

    namespace = f"test_champion_e2e_qdrant_{uuid.uuid4().hex[:10]}"
    monkeypatch.setenv("QUENTIN_MEMORY_STORE", "champion")
    monkeypatch.setenv("PG_DSN", dsn)
    monkeypatch.setenv("QDRANT_URL", qdrant_url)
    monkeypatch.setenv("QUENTIN_MEMORY_NAMESPACE", namespace)
    monkeypatch.setenv("MEM_EMBED_PROVIDER", "disabled")
    monkeypatch.setenv("MEM_EMBED_DIM", "16")
    monkeypatch.setenv("QUENTIN_QDRANT_WAIT_READY", "1")
    monkeypatch.setenv("QUENTIN_CHAMPION_STORE_VECTORS_IN_PG", "1")

    fabric = MemoryFabric(repo_root=tmp_path)
    store = fabric.store

    try:
        v1 = [1.0] + [0.0] * 15
        v2 = [0.0, 1.0] + [0.0] * 14
        r1 = fabric.remember_atomic(content="champion e2e target", source="test", vector=v1, domain="core")
        _r2 = fabric.remember_atomic(content="champion e2e distractor", source="test", vector=v2, domain="core")

        # Qdrant upsert is async in current implementation.
        time.sleep(0.25)
        out = fabric.recall(MemoryQuery(vector=v1, mode="vector_only", top_k=5))
        ids = [r.id for r in out]
        assert r1.id in ids
        assert bool(getattr(store, "_vec_ready", False)) is True
    finally:
        if hasattr(store, "cleanup_namespace"):
            store.cleanup_namespace(drop_collection=True)


def test_champion_store_vector_fallback_to_postgres_when_qdrant_unavailable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    dsn = _pg_dsn_from_env_or_default()
    if not _pg_ready(dsn):
        pytest.skip("Postgres not ready for champion fallback e2e test.")

    namespace = f"test_champion_e2e_fallback_{uuid.uuid4().hex[:10]}"
    monkeypatch.setenv("QUENTIN_MEMORY_STORE", "champion")
    monkeypatch.setenv("PG_DSN", dsn)
    monkeypatch.setenv("QDRANT_URL", "http://127.0.0.1:1")
    monkeypatch.setenv("QUENTIN_MEMORY_NAMESPACE", namespace)
    monkeypatch.setenv("MEM_EMBED_PROVIDER", "disabled")
    monkeypatch.setenv("MEM_EMBED_DIM", "16")
    monkeypatch.setenv("QUENTIN_QDRANT_WAIT_READY", "1")
    # Required so fallback vector search in Postgres has vectors available.
    monkeypatch.setenv("QUENTIN_CHAMPION_STORE_VECTORS_IN_PG", "1")

    fabric = MemoryFabric(repo_root=tmp_path)
    store = fabric.store

    try:
        v1 = [1.0] + [0.0] * 15
        v2 = [0.0, 1.0] + [0.0] * 14
        r1 = fabric.remember_atomic(content="champion fallback target", source="test", vector=v1, domain="core")
        _r2 = fabric.remember_atomic(content="champion fallback distractor", source="test", vector=v2, domain="core")

        out = fabric.recall(MemoryQuery(vector=v1, mode="vector_only", top_k=5))
        ids = [r.id for r in out]
        assert r1.id in ids
        assert bool(getattr(store, "_vec_ready", False)) is False
    finally:
        if hasattr(store, "cleanup_namespace"):
            store.cleanup_namespace(drop_collection=False)
