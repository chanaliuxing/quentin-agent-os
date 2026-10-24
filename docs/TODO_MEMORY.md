Memory Fabric / Sleep Loop TODO (Blueprint Alignment)
=====================================================

☑ **Vector & relations enrichment**
  - Auto-embeddings on writes + recall-side query embedding injection: `quentin/memory/fabric.py`.
  - Persist/return `relations` (SQLite/Postgres): `quentin/memory/store_sqlite.py`, `quentin/memory/store_postgres.py`.
  - Tests: vector search (SQLite/Postgres): `tests/unit/test_memory_store_sqlite.py`, `tests/unit/test_memory_store_postgres.py`.

☑ **PostgreSQL-backed MemoryStore**
已落地 PostgreSQL 集成与记忆栈改造，并补充验证（默认保守：仅在显式启用时使用 Postgres）：

  - MemoryFabric：可选 Postgres 存储（`PG_DSN` 或 `PG_HOST/PG_PORT/PG_USER/PG_PASSWORD/PG_DB`，并显式设置 `QUENTIN_MEMORY_STORE=postgres` 或 `USE_POSTGRES_MEMORY=1`）。
    保留 trace 打点、访问计数更新、kind/vector/relations 支持：`quentin/memory/fabric.py`.
  - 新增 quentin/memory/store_postgres.py（psycopg，JSONB 存储向量与关系，支持客户端余弦向量检索）；SQLite 存储同步扩展了
    kind/vector/relations 列、余弦向量检索、线程安全连接。
  - SleepLoop：恢复/增强巩固逻辑（政策覆盖、to_thread 调用、LTS 升级、训练对与技能候选 JSONL 输出、trace 事件、配置路径/阈
    值）；Report 增加统计字段。
  - TraceEventType 增加 MEMORY 类型。
  - 新增/调整单测：SQLite 向量检索、SleepLoop 巩固产出；Postgres 存储单测（需 PG_MEMORY_TEST=1 与 PG_* 环境启用才跑）。
  
  - Add a Postgres MemoryStore (psycopg/asyncpg) with schema matching MemoryRecord (tier/kind/vector/relations).
  - Support pgvector for vector search; text search via GIN/trigram as fallback.
  - Wire MemoryFabric to choose SQLite/Postgres via config/env (.env PG_*), add migrations and connection pool.
  - Tests: CRUD, promotion/decay, vector recall on Postgres.

☑ **Metrics & Research integration**
  - Observability 聚合 memory 事件（remember/recall/promote/decay）与 SleepLoop v3 outputs（training_pairs/skill_candidates）：`quentin/observability/service.py`.
  - Tests: `tests/unit/test_observability_memory_metrics.py`.

☑ **Training pairs & Skill pipeline**
  - SleepLoop v3 outputs 写入 `schema_version="v1"`：`quentin/memory/sleep_loop.py`.
  - Skill candidates ingestion：`quentin/skills/ingest.py`（默认读取 `data/training_pairs/skill_candidates.jsonl`，带去重日志）。
  - Optional auto-ingest: `quentin/memory/sleep_loop.py`（注入 `skill_library` 时自动注册）。
  - Tests: `tests/unit/test_sleep_loop_consolidation.py`, `tests/unit/test_skill_candidate_ingest.py`.

☑ **SleepLoop strategy & scheduling**
  - Config budget caps：`max_duration_ms` / `max_tokens_est`；policy knob：`consolidation_policy`：`quentin/memory/sleep_loop.py`.
  - 支持 `consolidation_policy="cluster"|"simple"`（便于 A/B 对比）。

☑ **Legacy cleanup**
  - `quentin/loops/sleep_loop.py` 变为兼容 wrapper，委托 canonical `quentin/memory/sleep_loop.py`（`quentin/core/sleep_loop.py` 已移除）。
  - `quentin/bootstrap/container.py` 仅实例化 canonical SleepLoop（已保持）。

☑ **Datetime hygiene**
  - Memory/skills/metrics 相关新增与关键路径改为 `now_utc()`：`quentin/utils/time.py`, `quentin/skills/schemas.py`, `quentin/infra/metrics.py`.

☑ **Embedding-enabled recall**
  - recall 会在 query.text 存在时自动注入 query embedding（embedding client 可用时）：`quentin/memory/fabric.py`.
  - CLI（显式开关向量召回）由 `qctl memory-recall` 提供（新增）。

---

OpenClaw-Inspired Memory Enhancements (2026-02-05) - Status
==========================================================

This section is a reconciliation of the "Memory 模块工程增强（参考 OpenClaw 思路）" checklist against the current repo.

- [x] M0 canonical paths + schema adapters
- [x] Schema adapter exists: `quentin/memory/adapters.py`

- [x] M1 Hybrid recall (text + vector)
- [x] `MemoryQuery.mode`: `auto | vector_only | text_only | hybrid`
- [x] Weighted re-rank with `alpha`, `k_text/k_vec`, score normalization + trace debug: `quentin/memory/fabric.py`
- [x] Unit tests: `tests/unit/test_memory_hybrid_recall.py`, `tests/unit/test_memory_recall_variant.py`

- [x] M2 Optional SQLite vec backend (sqlite-vec)
- [x] Store implemented with fallback: `quentin/memory/store_sqlite_vec.py`
- [x] Store selectable via env: `QUENTIN_MEMORY_STORE=sqlite_vec`

- [x] M3 Embedding provider fallback + health metrics
- [x] `FallbackEmbeddingClient` + env factory + health snapshot: `quentin/infra/llm/embeddings.py`

- [x] M4 Session deltas incremental STS writes (guarded + throttled)
- [x] Guarded writer with budget/safety: `quentin/memory/session_deltas.py`

- [x] M5 Reindex/swap for vec backend
- [x] `SqliteVecMemoryStore.reindex_indexes`: rebuild + swap tables

- [x] M1.3 micro benchmark (latency + hit@k)
- [x] Script: `scripts/bench_memory_recall.py`; Output to `data/bench/` and document runbook in `docs/bench_memory_recall.md` (do not commit artifacts).
