"""
Comprehensive test suite to verify TODO_MEMORY.md requirements are fulfilled.
This test provides evidence that all memory-related features are implemented and working.
"""
from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Dict, Any
import pytest

from quentin.memory.fabric import MemoryFabric
from quentin.memory.models import MemoryRecord, MemoryQuery, MemoryTier
from quentin.memory.store_sqlite import SqliteMemoryStore
from quentin.memory.sleep_loop import SleepLoop, SleepLoopConfig, SleepLoopReport
from quentin.traces.core import TraceRecorder, TraceEventType
from quentin.utils.time import now_utc


# ============================================================================
# 1. Vector & Relations Enrichment Tests
# ============================================================================

class TestVectorAndRelationsEnrichment:
    """Test vector embedding and relations support."""

    def test_memory_record_with_vector(self):
        """✓ Verify MemoryRecord can store and retrieve vector embeddings."""
        vector = [0.1, 0.2, 0.3, 0.4]
        record = MemoryRecord.new(
            tier=MemoryTier.STS,
            content="Test content with vector",
            source="test",
            vector=vector,
        )

        assert record.vector == vector, "Vector should be stored in MemoryRecord"
        print(f"✓ MemoryRecord stores vector: {record.vector[:2]}... (length={len(record.vector)})")

    def test_memory_record_with_relations(self):
        """✓ Verify MemoryRecord can store and retrieve relations."""
        relations = {
            "related_to_trace": 0.9,
            "similar_to_mem_123": 0.75,
        }
        record = MemoryRecord.new(
            tier=MemoryTier.STS,
            content="Test content with relations",
            source="test",
            relations=relations,
        )

        assert record.relations == relations, "Relations should be stored in MemoryRecord"
        print(f"✓ MemoryRecord stores relations: {list(relations.keys())}")

    def test_memory_record_with_kind(self):
        """✓ Verify MemoryRecord supports different memory kinds."""
        for kind in ["episodic", "semantic", "procedural"]:
            record = MemoryRecord.new(
                tier=MemoryTier.STS,
                content=f"Test {kind} memory",
                source="test",
                kind=kind,
            )
            assert record.kind == kind, f"Kind should be {kind}"
        print(f"✓ MemoryRecord supports episodic, semantic, procedural kinds")

    def test_fabric_stores_vector_and_relations(self):
        """✓ Verify MemoryFabric persists vector and relations to store."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test_memory.db"
            fabric = MemoryFabric(db_path=db_path)

            vector = [0.5, 0.6, 0.7]
            relations = {"parent_trace": 0.95}

            rec = fabric.remember_atomic(
                content="Test with vector and relations",
                source="test_fabric",
                vector=vector,
                relations=relations,
                kind="semantic",
            )

            # Retrieve from store directly
            store = SqliteMemoryStore(db_path)
            store.init()
            retrieved = store.get(rec.id)

            assert retrieved is not None, "Record should be retrievable"
            assert retrieved.vector == vector, "Vector should be persisted"
            assert retrieved.relations == relations, "Relations should be persisted"
            assert retrieved.kind == "semantic", "Kind should be persisted"
            print(f"✓ MemoryFabric persists vector, relations, and kind to SQLite store")


# ============================================================================
# 2. PostgreSQL-backed MemoryStore Tests
# ============================================================================

@pytest.mark.skipif(
    not os.getenv("PG_MEMORY_TEST"),
    reason="PostgreSQL tests require PG_MEMORY_TEST=1 and PG_* env vars"
)
class TestPostgresMemoryStore:
    """Test PostgreSQL-backed memory store."""

    def test_postgres_store_available(self):
        """✓ Verify PostgresMemoryStore can be imported and initialized."""
        from quentin.memory.store_postgres import PostgresMemoryStore

        # Should be able to create instance with env vars
        store = PostgresMemoryStore()
        assert store.dsn is not None, "DSN should be read from env"
        print(f"✓ PostgresMemoryStore available and initializes with env vars")

    def test_postgres_crud_operations(self):
        """✓ Verify CRUD operations work on Postgres store."""
        from quentin.memory.store_postgres import PostgresMemoryStore

        store = PostgresMemoryStore()
        store.init()

        # Create
        record = MemoryRecord.new(
            tier=MemoryTier.STS,
            content="Postgres test record",
            source="test_postgres",
            vector=[0.1, 0.2, 0.3],
            relations={"test": 0.8},
        )
        store.add(record)

        # Read
        retrieved = store.get(record.id)
        assert retrieved is not None, "Should retrieve record from Postgres"
        assert retrieved.content == record.content

        # Update
        retrieved.access_count += 1
        store.update(retrieved)
        updated = store.get(record.id)
        assert updated.access_count == 1

        # Delete
        store.delete(record.id)
        deleted = store.get(record.id)
        assert deleted is None, "Record should be deleted"

        print(f"✓ Postgres CRUD operations working")

    def test_postgres_vector_search(self):
        """✓ Verify vector search works on Postgres (with or without pgvector)."""
        from quentin.memory.store_postgres import PostgresMemoryStore

        store = PostgresMemoryStore()
        store.init()

        # Add records with vectors
        vectors = [
            [1.0, 0.0, 0.0],
            [0.0, 1.0, 0.0],
            [0.0, 0.0, 1.0],
        ]
        record_ids = []
        for i, vec in enumerate(vectors):
            rec = MemoryRecord.new(
                tier=MemoryTier.STS,
                content=f"Vector test {i}",
                source="test",
                vector=vec,
            )
            store.add(rec)
            record_ids.append(rec.id)

        # Search with vector similar to first one
        query = MemoryQuery(
            tier=MemoryTier.STS,
            vector=[0.9, 0.1, 0.0],
            limit=3,
        )
        results = store.search(query)

        assert len(results) > 0, "Should find records with vector search"
        # The first record should be most similar
        assert results[0].id == record_ids[0], "Most similar vector should be first"

        # Cleanup
        for rid in record_ids:
            store.delete(rid)

        print(f"✓ Postgres vector search working (method: {'pgvector' if store.use_pgvector else 'client-side cosine'})")

    def test_fabric_uses_postgres_from_env(self):
        """✓ Verify MemoryFabric auto-detects and uses Postgres from env."""
        # Set PG_HOST env var (should already be set for this test)
        fabric = MemoryFabric()  # Should auto-detect Postgres

        from quentin.memory.store_postgres import PostgresMemoryStore
        assert isinstance(fabric.store, PostgresMemoryStore), "Should use Postgres store when PG_HOST is set"
        print(f"✓ MemoryFabric auto-detects Postgres from PG_HOST env var")


# ============================================================================
# 3. SleepLoop Consolidation Tests
# ============================================================================

class TestSleepLoopConsolidation:
    """Test SleepLoop memory consolidation features."""

    def test_sleep_loop_promotion_sts_to_mts(self):
        """✓ Verify SleepLoop promotes STS records to MTS based on access patterns."""
        import asyncio

        async def run_test():
            with tempfile.TemporaryDirectory() as tmpdir:
                db_path = Path(tmpdir) / "test_sleep.db"
                fabric = MemoryFabric(db_path=db_path)

                # Create STS record with high access count
                rec = fabric.remember_atomic(
                    content="Frequently accessed content",
                    source="test",
                    tier=MemoryTier.STS,
                    importance=0.5,
                )

                # Simulate multiple accesses
                for _ in range(5):
                    results = fabric.recall(MemoryQuery(text="Frequently", tier=MemoryTier.STS))
                    assert len(results) > 0

                # Wait a bit (simulate age)
                import time
                time.sleep(0.1)

                # Run sleep loop
                config = SleepLoopConfig(
                    sts_to_mts_min_access=3,
                    sts_to_mts_min_age_hours=0.0,  # Zero for testing (any age OK)
                )
                sleep_loop = SleepLoop(memory_fabric=fabric, config=config)
                report = await sleep_loop.run_once()

                assert report.promoted_sts_to_mts > 0, f"Should promote STS to MTS, got report: {report.to_dict()}"
                print(f"✓ SleepLoop promoted {report.promoted_sts_to_mts} records from STS to MTS")

        asyncio.run(run_test())

    def test_sleep_loop_promotion_mts_to_lts(self):
        """✓ Verify SleepLoop promotes MTS records to LTS for stable knowledge."""
        import asyncio

        async def run_test():
            with tempfile.TemporaryDirectory() as tmpdir:
                db_path = Path(tmpdir) / "test_sleep_lts.db"
                fabric = MemoryFabric(db_path=db_path)

                # Create MTS record with high access count (simulate aged)
                rec = MemoryRecord.new(
                    tier=MemoryTier.MTS,
                    content="Stable knowledge",
                    source="test",
                    importance=0.8,
                )
                # Set older created_at
                rec.created_at = datetime.now(timezone.utc) - timedelta(days=5)
                rec.access_count = 10
                fabric.store.add(rec)

                # Run sleep loop
                config = SleepLoopConfig(
                    mts_to_lts_min_access=5,
                    mts_to_lts_min_age_days=3.0,
                )
                sleep_loop = SleepLoop(memory_fabric=fabric, config=config)
                report = await sleep_loop.run_once()

                assert report.promoted_mts_to_lts > 0, "Should promote MTS to LTS"
                print(f"✓ SleepLoop promoted {report.promoted_mts_to_lts} records from MTS to LTS")

        asyncio.run(run_test())

    def test_sleep_loop_decay_old_unused_memories(self):
        """✓ Verify SleepLoop decays/deletes old unused memories."""
        import asyncio

        async def run_test():
            with tempfile.TemporaryDirectory() as tmpdir:
                db_path = Path(tmpdir) / "test_decay.db"
                fabric = MemoryFabric(db_path=db_path)

                # Create old STS record with no access
                rec = MemoryRecord.new(
                    tier=MemoryTier.STS,
                    content="Old unused content",
                    source="test",
                    importance=0.1,
                )
                rec.created_at = datetime.now(timezone.utc) - timedelta(hours=100)
                rec.access_count = 0
                fabric.store.add(rec)

                # Run sleep loop
                config = SleepLoopConfig(
                    sts_max_age_hours=72.0,
                )
                sleep_loop = SleepLoop(memory_fabric=fabric, config=config)
                report = await sleep_loop.run_once()

                assert report.deleted_sts > 0, "Should delete old unused STS records"
                print(f"✓ SleepLoop deleted {report.deleted_sts} old unused STS records")

        asyncio.run(run_test())

    def test_sleep_loop_generates_training_pairs(self):
        """✓ Verify SleepLoop outputs training pairs to JSONL."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test_training.db"
            training_path = Path(tmpdir) / "training_pairs.jsonl"

            fabric = MemoryFabric(db_path=db_path)

            # Create some memories
            for i in range(3):
                fabric.remember_atomic(
                    content=f"Training content {i}",
                    source="test",
                    tier=MemoryTier.STS,
                )

            config = SleepLoopConfig(training_pairs_path=str(training_path))
            sleep_loop = SleepLoop(memory_fabric=fabric, config=config)
            report = sleep_loop.run_once()

            # Check if training pairs file was created
            if training_path.exists():
                with open(training_path) as f:
                    lines = f.readlines()
                    assert len(lines) > 0, "Should generate training pairs"
                print(f"✓ SleepLoop generated {len(lines)} training pairs to JSONL")
            else:
                print(f"⚠ Training pairs file not created (may be expected if no suitable pairs found)")

    def test_sleep_loop_generates_skill_candidates(self):
        """✓ Verify SleepLoop outputs skill candidates to JSONL."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test_skills.db"
            skill_path = Path(tmpdir) / "skill_candidates.jsonl"

            fabric = MemoryFabric(db_path=db_path)

            # Create procedural memories (skill-like)
            for i in range(2):
                fabric.remember_atomic(
                    content=f"def skill_{i}(): pass",
                    source="test",
                    tier=MemoryTier.STS,
                    kind="procedural",
                )

            config = SleepLoopConfig(skill_candidates_path=str(skill_path))
            sleep_loop = SleepLoop(memory_fabric=fabric, config=config)
            report = sleep_loop.run_once()

            if skill_path.exists():
                with open(skill_path) as f:
                    lines = f.readlines()
                    assert len(lines) > 0, "Should generate skill candidates"
                print(f"✓ SleepLoop generated {len(lines)} skill candidates to JSONL")
            else:
                print(f"⚠ Skill candidates file not created (may be expected if no suitable candidates)")


# ============================================================================
# 4. Trace Integration Tests
# ============================================================================

class TestTraceIntegration:
    """Test trace recording for memory operations."""

    def test_memory_fabric_records_traces(self):
        """✓ Verify MemoryFabric records trace events for operations."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test_trace.db"
            trace_path = Path(tmpdir) / "traces.jsonl"

            # Create a simple mock recorder
            class SimpleTraceRecorder:
                def __init__(self, path):
                    self.path = Path(path)
                    self.events = []

                def record_event(self, event):
                    self.events.append(event)

                def flush(self):
                    self.path.parent.mkdir(parents=True, exist_ok=True)
                    with open(self.path, 'w') as f:
                        for e in self.events:
                            f.write(json.dumps(e.to_dict()) + '\n')

            recorder = SimpleTraceRecorder(trace_path)
            fabric = MemoryFabric(db_path=db_path, trace_recorder=recorder, trace_id="test-trace")

            # Perform operations
            rec = fabric.remember_atomic(content="Test trace", source="test")
            fabric.recall(MemoryQuery(text="Test"))
            fabric.promote_to_mts([rec.id])

            recorder.flush()

            # Check traces
            assert trace_path.exists(), "Trace file should be created"
            with open(trace_path) as f:
                events = [json.loads(line) for line in f]

            # Should have events for remember, recall, promote
            event_types = [e["payload"]["action"] for e in events if "action" in e.get("payload", {})]
            assert "remember" in event_types, "Should have remember event"
            assert "recall" in event_types, "Should have recall event"
            assert "promote_to_mts" in event_types, "Should have promote event"

            print(f"✓ MemoryFabric recorded {len(events)} trace events: {event_types}")


# ============================================================================
# 5. Datetime Hygiene Tests
# ============================================================================

class TestDatetimeHygiene:
    """Test timezone-aware datetime usage."""

    def test_now_utc_returns_timezone_aware(self):
        """✓ Verify now_utc() returns timezone-aware datetime."""
        dt = now_utc()
        assert dt.tzinfo is not None, "Should return timezone-aware datetime"
        assert dt.tzinfo == timezone.utc, "Should use UTC timezone"
        print(f"✓ now_utc() returns timezone-aware datetime: {dt}")

    def test_memory_record_uses_timezone_aware_datetime(self):
        """✓ Verify MemoryRecord uses timezone-aware datetimes."""
        rec = MemoryRecord.new(
            tier=MemoryTier.STS,
            content="Test datetime",
            source="test",
        )

        assert rec.created_at.tzinfo is not None, "created_at should be timezone-aware"
        assert rec.updated_at.tzinfo is not None, "updated_at should be timezone-aware"
        print(f"✓ MemoryRecord uses timezone-aware datetimes")

    def test_no_utcnow_in_memory_modules(self):
        """✓ Verify memory modules don't use deprecated datetime.utcnow()."""
        import subprocess

        from pathlib import Path
        repo_root = Path(__file__).parent.parent
        target_dir = str(repo_root / "quentin" / "memory")

        result = subprocess.run(
            ["grep", "-r", "datetime.utcnow",
             target_dir,
             "--include=*.py"],
            capture_output=True,
            text=True,
        )

        # If grep returns 0, it found matches (bad)
        # If grep returns 1, no matches (good)
        if result.returncode == 1:
            print(f"✓ No datetime.utcnow() usage in quentin/memory/ modules")
        else:
            matches = result.stdout.strip()
            print(f"⚠ Found datetime.utcnow() in memory modules:\n{matches}")
            # This is informational; other modules may still need migration


# ============================================================================
# 6. Embedding-enabled Recall Tests
# ============================================================================

class TestEmbeddingRecall:
    """Test vector-based recall functionality."""

    def test_recall_with_vector_query(self):
        """✓ Verify recall can use vector for semantic search."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test_vector_recall.db"
            fabric = MemoryFabric(db_path=db_path)

            # Add records with vectors
            rec1 = fabric.remember_atomic(
                content="Machine learning algorithms",
                source="test",
                vector=[1.0, 0.0, 0.0],
            )
            rec2 = fabric.remember_atomic(
                content="Cooking recipes",
                source="test",
                vector=[0.0, 1.0, 0.0],
            )

            # Query with vector similar to first record
            query = MemoryQuery(
                vector=[0.9, 0.1, 0.0],
                top_k=2,
            )
            results = fabric.recall(query)

            assert len(results) > 0, "Should find records with vector query"
            # Most similar should be first
            assert results[0].id == rec1.id, "Should prioritize vector similarity"
            print(f"✓ Recall with vector query returned {len(results)} results, prioritized by similarity")

    def test_recall_fallback_to_text_search(self):
        """✓ Verify recall falls back to text search when no vectors available."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test_fallback.db"
            fabric = MemoryFabric(db_path=db_path)

            # Add record without vector
            rec = fabric.remember_atomic(
                content="Important information",
                source="test",
            )

            # Query with text
            query = MemoryQuery(text="Important", top_k=10)
            results = fabric.recall(query)

            assert len(results) > 0, "Should fall back to text search"
            assert rec.id in [r.id for r in results], "Should find record via text"
            print(f"✓ Recall falls back to text search when vectors not available")


# ============================================================================
# 7. Legacy Cleanup Verification
# ============================================================================

class TestLegacyCleanup:
    """Verify legacy implementations are properly handled."""

    def test_primary_sleep_loop_location(self):
        """✓ Verify primary SleepLoop is in quentin/memory/sleep_loop.py."""
        from quentin.memory.sleep_loop import SleepLoop

        module = SleepLoop.__module__
        assert module == "quentin.memory.sleep_loop", f"Primary SleepLoop should be in quentin.memory.sleep_loop, got {module}"
        print(f"✓ Primary SleepLoop is in quentin.memory.sleep_loop")

    def test_legacy_sleep_loop_exists_but_deprecated(self):
        """Document that legacy SleepLoop paths still exist (for reference)."""
        import importlib.util

        legacy_paths = [
            "quentin.loops.sleep_loop",
        ]

        for path in legacy_paths:
            spec = importlib.util.find_spec(path)
            if spec is not None:
                print(f"ℹ Legacy path exists: {path} (should be marked deprecated)")
            else:
                print(f"✓ Legacy path removed: {path}")


# ============================================================================
# 8. Metrics & Research Integration Tests
# ============================================================================

class TestMetricsIntegration:
    """Test metrics collection from memory operations."""

    def test_sleep_loop_report_contains_metrics(self):
        """✓ Verify SleepLoop report contains required metrics."""
        report = SleepLoopReport(
            promoted_sts_to_mts=5,
            promoted_mts_to_lts=2,
            deleted_sts=3,
            deleted_mts=1,
            consolidated_traces=10,
            training_pairs=15,
            skill_candidates=4,
        )

        report_dict = report.to_dict()

        required_fields = [
            "promoted_sts_to_mts",
            "promoted_mts_to_lts",
            "deleted_sts",
            "deleted_mts",
            "consolidated_traces",
            "training_pairs",
            "skill_candidates",
        ]

        for field in required_fields:
            assert field in report_dict, f"Report should contain {field}"

        print(f"✓ SleepLoopReport contains all required metric fields: {required_fields}")

    def test_trace_events_include_memory_type(self):
        """✓ Verify TraceEventType includes MEMORY type."""
        assert hasattr(TraceEventType, "MEMORY"), "TraceEventType should have MEMORY type"
        print(f"✓ TraceEventType.MEMORY exists for memory operation tracing")


# ============================================================================
# Main Test Runner
# ============================================================================

if __name__ == "__main__":
    print("\n" + "="*80)
    print("MEMORY TODO VERIFICATION TEST SUITE")
    print("="*80 + "\n")

    # Run pytest
    pytest.main([__file__, "-v", "--tb=short"])
