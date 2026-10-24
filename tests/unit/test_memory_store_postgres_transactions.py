from __future__ import annotations

from datetime import datetime, timezone

from quentin.memory.models import MemoryQuery, MemoryTier
from quentin.memory.store_postgres import PostgresMemoryStore


class _FakeCursor:
    def __init__(self, rows):
        self._rows = list(rows)

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return list(self._rows)


class _FakeConn:
    def __init__(self, rows):
        self.rows = list(rows)
        self.commit_calls = 0
        self.executed = []

    def execute(self, sql, params=None):
        self.executed.append((str(sql), params))
        return _FakeCursor(self.rows)

    def commit(self):
        self.commit_calls += 1


def _row():
    now = datetime.now(timezone.utc)
    return {
        "id": "r1",
        "tier": MemoryTier.STS.value,
        "kind": "episodic",
        "topic": None,
        "content": "hello",
        "created_at": now,
        "updated_at": now,
        "source": "test",
        "domain": "core",
        "importance": 0.5,
        "last_accessed_at": None,
        "access_count": 0,
        "tags": [],
        "metadata": {},
        "consolidated_from_ids": [],
        "supersedes_ids": [],
        "vector": None,
        "vector_emb": None,
        "relations": {},
    }


def test_get_commits_after_read() -> None:
    store = PostgresMemoryStore(dsn="postgresql://unused", use_pgvector=False)
    fake = _FakeConn([_row()])
    store._conn = fake  # type: ignore[assignment]

    rec = store.get("r1")

    assert rec is not None
    assert fake.commit_calls == 1


def test_search_commits_after_read() -> None:
    store = PostgresMemoryStore(dsn="postgresql://unused", use_pgvector=False)
    fake = _FakeConn([_row()])
    store._conn = fake  # type: ignore[assignment]

    out = store.search(MemoryQuery(text="hello", top_k=5))

    assert len(out) == 1
    assert fake.commit_calls == 1
