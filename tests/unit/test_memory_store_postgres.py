import os
import pytest

psycopg = pytest.importorskip("psycopg")  # Ensure dependency available
pgvector = pytest.importorskip("pgvector")  # Require pgvector package

from quentin.memory.store_postgres import PostgresMemoryStore
from quentin.memory.models import MemoryRecord, MemoryTier, MemoryQuery


def _build_dsn():
    if os.getenv("PG_MEMORY_TEST") != "1":
        pytest.skip("PG_MEMORY_TEST not enabled; skipping Postgres store tests.")
    dsn = os.getenv("PG_DSN")
    if dsn:
        return dsn
    host = os.getenv("PG_HOST")
    if not host:
        pytest.skip("PG_HOST not set for Postgres store tests.")
    port = os.getenv("PG_PORT", "5432")
    user = os.getenv("PG_USER", "postgres")
    password = os.getenv("PG_PASSWORD", "")
    db = os.getenv("PG_DB", "postgres")
    return f"postgresql://{user}:{password}@{host}:{port}/{db}"


def _clean(store: PostgresMemoryStore):
    try:
        store.conn.execute("TRUNCATE TABLE memories;")
        store.conn.commit()
    except Exception:
        pass


@pytest.fixture
def pg_store():
    dsn = _build_dsn()
    store = PostgresMemoryStore(dsn=dsn, use_pgvector=False)
    store.init()
    _clean(store)
    yield store
    _clean(store)


def test_postgres_store_crud_and_vector(pg_store: PostgresMemoryStore):
    rec = MemoryRecord.new(
        tier=MemoryTier.STS,
        content="hello pg",
        source="test",
        vector=[1.0, 0.0],
        kind="episodic",
        tags=["t1"],
    )
    pg_store.add(rec)

    fetched = pg_store.get(rec.id)
    assert fetched is not None
    assert fetched.content == "hello pg"

    query = MemoryQuery(vector=[1.0, 0.0], top_k=1)
    res = pg_store.search(query)
    assert res and res[0].id == rec.id

    pg_store.promote(rec.id, MemoryTier.MTS)
    promoted = pg_store.get(rec.id)
    assert promoted.tier == MemoryTier.MTS

    pg_store.mark_decayed(rec.id)
    assert pg_store.get(rec.id) is None


def test_postgres_store_vector_pgvector_enabled():
    dsn = _build_dsn()
    store = PostgresMemoryStore(dsn=dsn, use_pgvector=True)
    store.init()
    _clean(store)

    rec_a = MemoryRecord.new(
        tier=MemoryTier.STS,
        content="vecA",
        source="test",
        vector=[1.0, 0.0],
    )
    rec_b = MemoryRecord.new(
        tier=MemoryTier.STS,
        content="vecB",
        source="test",
        vector=[0.0, 1.0],
    )
    store.add(rec_a)
    store.add(rec_b)

    res = store.search(MemoryQuery(vector=[1.0, 0.0], top_k=1))
    assert res
    assert res[0].id == rec_a.id
