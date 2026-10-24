# Memory Module Engineering Enhancements (OpenClaw-inspired) — Actionable TODO

Date: 2026-02-08
Related:
- Blueprint checklist: `docs/TODO_BLUEPRINT_V3_CHECKLIST.md`
- Gap analysis: `docs/BLUEPRINT_GAP_ANALYSIS_V3.md`
- OpenClaw patterns: `docs/improve/openclaw_takeaways_for_quentin.md`

Goal:
- Keep `blueprint.md` as the main narrative.
- Track Memory engineering enhancements as executable tasks with clear DoD.

Notes (conflict resolution / repo reality):
- Canonical SleepLoop entrypoint is `quentin/sleep/loop_impl.py:SleepLoop`.
  - `quentin/memory/sleep_loop.py` is a compat import path only.
- Gemini-mentioned `meta_agent/memory/context_provider.py` exists (not missing).

---

## M0: Canonical path & schema unification (avoid fragmentation)

- [x] Canonical `MemoryFabric` path is stable
  - File: `quentin/memory/fabric.py:MemoryFabric`
  - DoD: runtime/container/CLI import this as the authoritative implementation.

- [x] Canonical `SleepLoop` path is stable
  - Files: `quentin/sleep/loop_impl.py:SleepLoop`, `quentin/sleep/loop.py`
  - DoD: older paths delegate/compat only.

- [x] Single Memory schema for storage + retrieval
  - File: `quentin/memory/models.py` (`MemoryRecord`, `MemoryUpdatePolicy`, `MemoryQuery`)
  - DoD: store implementations serialize `update_policy` consistently.

---

## M1: Hybrid recall (Text + Vector) with explainable scoring

- [x] Hybrid recall modes and parameters
  - File: `quentin/memory/models.py:MemoryQuery` (`mode`, `alpha`, `k_text`, `k_vec`, `min_*`, `text_mode`, `debug`)
  - DoD: can force `text_only` without auto-embedding override.

- [x] Two-path recall + union + normalized re-rank
  - File: `quentin/memory/fabric.py:MemoryFabric.recall`
  - DoD: hybrid can include keyword-only hits and vector-only hits in same top-k.

- [x] Trace/debug payload for ranking explainability (env-gated)
  - File: `quentin/memory/fabric.py` (`debug_payload` under recall trace)
  - DoD: `QUENTIN_MEMORY_DEBUG=1` shows per-candidate text/vector/combined scores.

- [x] Unit tests for hybrid modes
  - File: `tests/unit/test_memory_hybrid_recall.py`
  - DoD: `pytest tests/unit/test_memory_hybrid_recall.py -q` passes offline.

- [x] Recall benchmark script (offline)
  - File: `scripts/bench_memory_recall.py`
  - DoD: `pytest tests/integration/test_bench_memory_recall_runs.py -q` passes.

---

## M2: SQLite vector index backend (sqlite-vec) — optional, fallback-safe

- [x] Optional sqlite-vec store implementation with safe fallback
  - Files: `quentin/memory/store_sqlite_vec.py`, `quentin/memory/fabric.py` (store selection)
  - DoD: missing extension auto-falls back to standard SQLite store with warning.

- [x] Reindex/swap helper for sqlite-vec
  - File: `quentin/memory/store_sqlite_vec.py:reindex_indexes`
  - DoD: rebuild->swap path returns structured status and does not crash on failure.

---

## M3: Embedding provider fallback + health metrics

- [x] Fallback embedding client (multi-provider chain)
  - File: `quentin/infra/llm/embeddings.py:FallbackEmbeddingClient`
  - DoD: provider failures degrade to empty-vector (text-only paths still work).

- [x] Embedding health registry + observability hook
  - Files: `quentin/infra/llm/embeddings.py`, `quentin/observability/service.py`
  - DoD: embedding provider health snapshot is queryable without external deps.

---

## M4: Incremental write-in-flight (session deltas) — high-risk, budget-gated

- [ ] Add STS delta write trigger with throttle/debounce
  - Files: `quentin/runtime/brain_daemon.py` (or canonical loop), `quentin/memory/fabric.py`
  - DoD: long-running tasks can recall newly produced key facts, without STS exploding.

- [ ] SafetyKernel guard for delta embedding/write
  - DoD: delta writes are disabled by default; prod defaults remain off.

---

## M5: Index consistency & atomic reindex (FTS/sqlite-vec/pgvector)

- [ ] Atomic reindex for SQLite FTS (optional)
  - File: `quentin/memory/store_sqlite.py`
  - DoD: reindex does not block recall (best-effort) and is rollback-safe.

- [ ] Postgres concurrent index strategy (if pgvector enabled)
  - File: `quentin/memory/store_postgres.py`
  - DoD: `CONCURRENTLY` path documented and failure is non-fatal.

---

## M6: Research-friendly A/B + metrics for memory retrieval

- [ ] Variantize hybrid parameters (alpha/k/text_mode/backend)
  - Files: `quentin/l3/research/interface.py`, `quentin/l3/research/experiment_orchestrator.py`
  - DoD: the same eval set can compare variants and emit stable metrics (hit_rate/latency).

- [ ] Dashboard metrics: recall_hit_rate, embedding_fail_rate, recall_latency
  - File: `quentin/observability/service.py`
  - DoD: `get_overview` includes memory retrieval metrics (at least v1 counters/latency).

