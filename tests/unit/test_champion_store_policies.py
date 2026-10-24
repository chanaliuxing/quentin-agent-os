from __future__ import annotations

from quentin.memory.models import MemoryQuery, MemoryRecord, MemoryTier
from quentin.memory.store_champion import ChampionMemoryStore, QdrantRestClient


def _make_store(monkeypatch, **env):
    monkeypatch.setenv("PG_HOST", "localhost")
    monkeypatch.setenv("PG_PORT", "55432")
    monkeypatch.setenv("PG_USER", "postgres")
    monkeypatch.setenv("PG_PASSWORD", "postgres")
    monkeypatch.setenv("PG_DB", "quentin_memory")
    for k, v in env.items():
        monkeypatch.setenv(k, str(v))
    return ChampionMemoryStore()


def test_hot_policy_recent_days_sets_since(monkeypatch):
    store = _make_store(monkeypatch, QUENTIN_CHAMPION_HOT_POLICY="recent_days", QUENTIN_CHAMPION_HOT_RECENT_DAYS="7")
    q = MemoryQuery(text="hello", top_k=5)
    out = store._apply_hot_policy(q)
    assert out.since is not None


def test_hot_policy_sts_only_sets_tier(monkeypatch):
    store = _make_store(monkeypatch, QUENTIN_CHAMPION_HOT_POLICY="sts_only")
    q = MemoryQuery(text="hello", top_k=5)
    out = store._apply_hot_policy(q)
    assert out.tier == MemoryTier.STS


def test_filter_hot_tiers_sts_mts(monkeypatch):
    store = _make_store(monkeypatch, QUENTIN_CHAMPION_HOT_POLICY="sts_mts")
    r_sts = MemoryRecord.new(tier=MemoryTier.STS, content="a", source="t")
    r_mts = MemoryRecord.new(tier=MemoryTier.MTS, content="b", source="t")
    r_lts = MemoryRecord.new(tier=MemoryTier.LTS, content="c", source="t")
    out = store._filter_by_hot_tiers([r_sts, r_mts, r_lts])
    assert [r.id for r in out] == [r_sts.id, r_mts.id]


def test_lexical_reranker_prefers_exact(monkeypatch):
    store = _make_store(monkeypatch, QUENTIN_CHAMPION_RERANKER="lexical")
    r1 = MemoryRecord.new(tier=MemoryTier.STS, content="payments outage case 42", source="t")
    r2 = MemoryRecord.new(tier=MemoryTier.STS, content="generic notes", source="t")
    q = MemoryQuery(text="payments outage", top_k=2)
    out = store._apply_reranker(q, [r2, r1])
    assert out[0].id == r1.id


def test_hot_only_can_run_without_postgres(monkeypatch):
    for k in ("PG_DSN", "PG_HOST", "PG_PORT", "PG_USER", "PG_PASSWORD", "PG_DB"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("QUENTIN_CHAMPION_HOT_ONLY", "1")
    monkeypatch.setenv("QUENTIN_QDRANT_WAIT_READY", "0")
    monkeypatch.setattr(QdrantRestClient, "ensure_collection", lambda self, **kwargs: None)

    store = ChampionMemoryStore()
    store.init()

    assert store.get("missing") is None
    assert store.search(MemoryQuery(text="hello", top_k=3)) == []


def test_missing_postgres_auto_switches_to_hot_only(monkeypatch):
    for k in ("PG_DSN", "PG_HOST", "PG_PORT", "PG_USER", "PG_PASSWORD", "PG_DB"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.delenv("QUENTIN_CHAMPION_HOT_ONLY", raising=False)

    store = ChampionMemoryStore()
    assert store._hot_only is True
