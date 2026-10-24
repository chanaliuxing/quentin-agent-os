from pathlib import Path

from quentin.memory.batch_runner import MemoryBatchConfig, MemoryConsolidationBatchRunner
from quentin.memory.fabric import MemoryFabric
from quentin.memory.models import MemoryTier
from quentin.memory.policies import MemoryPolicyConfig, MemoryPolicyEngine


def test_memory_batch_promotes_and_decays(tmp_path: Path) -> None:
    db_path = tmp_path / "memory.db"
    fabric = MemoryFabric(db_path=db_path)

    # Create one STS record that should be promoted and one that should decay.
    r_promote = fabric.remember_atomic(
        content="promote_me",
        source="test",
        tier=MemoryTier.STS,
        importance=0.9,
    )
    r_decay = fabric.remember_atomic(
        content="decay_me",
        source="test",
        tier=MemoryTier.STS,
        importance=0.1,
    )

    # Manipulate access/age in-memory then persist.
    r_promote.access_count = 3
    r_promote.last_accessed_at = r_promote.created_at
    fabric.store.update(r_promote)

    r_decay.access_count = 0
    r_decay.last_accessed_at = r_decay.created_at
    fabric.store.update(r_decay)

    # Configure policy to promote quickly and decay immediately.
    policy = MemoryPolicyEngine(
        config=MemoryPolicyConfig(
            sts_to_mts_hits=1,
            sts_to_mts_age_minutes=0,
            mts_to_lts_hits=10,
            mts_to_lts_age_days=3,
            sts_ttl_minutes=0,
            mts_ttl_days=30,
        )
    )

    runner = MemoryConsolidationBatchRunner(
        fabric=fabric,
        policy_engine=policy,
        config=MemoryBatchConfig(
            enabled=True,
            batch_name="manual",
            max_records=50,
            max_duration_ms=10_000,
            max_tokens_est=1_000_000,
            enable_consolidation=False,
        ),
    )
    report = runner.run_once()

    assert report.promoted >= 1
    assert report.decayed >= 1

    # Promotion should move record to MTS; decay should mark record inaccessible.
    got_promote = fabric.store.get(r_promote.id)
    assert got_promote is not None
    assert got_promote.tier == MemoryTier.MTS

    got_decay = fabric.store.get(r_decay.id)
    assert got_decay is None


def test_memory_batch_is_idempotent_and_budgeted(tmp_path: Path) -> None:
    db_path = tmp_path / "memory.db"
    fabric = MemoryFabric(db_path=db_path)

    # Create several records that would be eligible for promotion.
    recs = []
    for i in range(10):
        r = fabric.remember_atomic(
            content=f"promote_{i}",
            source="test",
            tier=MemoryTier.STS,
            importance=0.9,
        )
        r.access_count = 3
        r.last_accessed_at = r.created_at
        fabric.store.update(r)
        recs.append(r)

    policy = MemoryPolicyEngine(
        config=MemoryPolicyConfig(
            sts_to_mts_hits=1,
            sts_to_mts_age_minutes=0,
            mts_to_lts_hits=10,
            mts_to_lts_age_days=3,
            sts_ttl_minutes=9999,
            mts_ttl_days=30,
        )
    )

    # Budget: allow at most 3 promotions/decays per run.
    runner = MemoryConsolidationBatchRunner(
        fabric=fabric,
        policy_engine=policy,
        config=MemoryBatchConfig(
            enabled=True,
            batch_name="manual",
            max_records=3,
            max_duration_ms=10_000,
            max_tokens_est=1_000_000,
            enable_consolidation=False,
        ),
    )

    first = runner.run_once()
    assert first.promoted == 3
    assert first.stopped_reason in ("max_records", "")

    # Second run should promote the next batch, not re-promote already promoted ones.
    second = runner.run_once()
    assert second.promoted == 3

    # Previously promoted records stay promoted and are not counted again.
    promoted_now = [fabric.store.get(r.id) for r in recs]
    promoted_now = [r for r in promoted_now if r is not None]
    assert sum(1 for r in promoted_now if r.tier == MemoryTier.MTS) == 6
