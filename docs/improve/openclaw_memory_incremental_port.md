# OpenClaw Memory Incremental Port Progress

## Ordered Read Checklist
- [x] `openclaw/openclaw/src/memory/batch-gemini.ts`
- [x] `openclaw/openclaw/src/memory/batch-openai.ts`
- [x] `openclaw/openclaw/src/memory/embeddings-gemini.ts`
- [x] `openclaw/openclaw/src/memory/embeddings-openai.ts`
- [x] `openclaw/openclaw/src/memory/embeddings.test.ts`
- [x] `openclaw/openclaw/src/memory/embeddings.ts`
- [x] `openclaw/openclaw/src/memory/headers-fingerprint.ts`
- [x] `openclaw/openclaw/src/memory/hybrid.test.ts`
- [x] `openclaw/openclaw/src/memory/hybrid.ts`
- [x] `openclaw/openclaw/src/memory/index.test.ts`
- [x] `openclaw/openclaw/src/memory/index.ts`
- [x] `openclaw/openclaw/src/memory/internal.test.ts`
- [x] `openclaw/openclaw/src/memory/internal.ts`
- [x] `openclaw/openclaw/src/memory/manager-cache-key.ts`
- [x] `openclaw/openclaw/src/memory/manager-search.ts`
- [x] `openclaw/openclaw/src/memory/manager.async-search.test.ts`
- [x] `openclaw/openclaw/src/memory/manager.atomic-reindex.test.ts`
- [x] `openclaw/openclaw/src/memory/manager.batch.test.ts`
- [x] `openclaw/openclaw/src/memory/manager.embedding-batches.test.ts`
- [x] `openclaw/openclaw/src/memory/manager.sync-errors-do-not-crash.test.ts`
- [x] `openclaw/openclaw/src/memory/manager.ts`
- [x] `openclaw/openclaw/src/memory/manager.vector-dedupe.test.ts`
- [x] `openclaw/openclaw/src/memory/memory-schema.ts`
- [x] `openclaw/openclaw/src/memory/node-llama.ts`
- [x] `openclaw/openclaw/src/memory/openai-batch.ts`
- [x] `openclaw/openclaw/src/memory/provider-key.ts`
- [x] `openclaw/openclaw/src/memory/search-manager.ts`
- [x] `openclaw/openclaw/src/memory/session-files.ts`
- [x] `openclaw/openclaw/src/memory/sqlite-vec.ts`
- [x] `openclaw/openclaw/src/memory/sqlite.ts`
- [x] `openclaw/openclaw/src/memory/status-format.ts`
- [x] `openclaw/openclaw/src/memory/sync-memory-files.ts`
- [x] `openclaw/openclaw/src/memory/sync-session-files.ts`

## Increment 1 Landed
- `provider-specific embedding batching`:
  - OpenAI multi-input batch path in `quentin/memory/embedding_batch.py`.
- `differential fingerprint cache`:
  - Persistent fingerprint cache in `quentin/memory/embedding_batch.py`.
- `batch write API`:
  - `remember_many_atomic` in `quentin/memory/fabric.py`.
- `provider-key partitioning`:
  - Cache key partition by provider+model+base URL/header fingerprint.
- `batch failure degradation`:
  - Batch failure counting and auto fallback to single embeddings after threshold.

## Increment 2 Landed
- `file_path + content_hash dedupe lock` in sync layer:
  - `quentin/infra/sessions/dirty_sync.py`
  - suppress duplicate concurrent sync callbacks for same fingerprint.

## Increment 3 Landed
- `openai async batch state machine`:
  - upload -> create batch -> poll -> download output
  - file: `quentin/memory/embedding_batch.py`
- `batch timeout/wait controls`:
  - env:
    - `MEM_EMBED_OPENAI_ASYNC_BATCH`
    - `MEM_EMBED_OPENAI_ASYNC_WAIT`
    - `MEM_EMBED_OPENAI_ASYNC_POLL_S`
    - `MEM_EMBED_OPENAI_ASYNC_TIMEOUT_S`
  - wired in: `quentin/memory/fabric.py`
- `batch fallback safety`:
  - async batch failures still degrade to single embeddings and obey failure-limit disabling.

## Increment 4 Landed
- `atomic reindex/swap` for SQLite memory store:
  - temp copy -> rebuild -> integrity check -> atomic swap -> rollback on failure
  - file: `quentin/memory/store_sqlite.py`
- behavior guarantees:
  - failed reindex keeps old DB untouched
  - successful reindex keeps data readable after swap

## Increment 5 Landed
- `session delta threshold sync`:
  - dual thresholds: `delta_bytes` + `delta_messages`
  - file: `quentin/memory/session_deltas.py`
- config/env support:
  - `QUENTIN_SESSION_DELTAS_DELTA_BYTES`
  - `QUENTIN_SESSION_DELTAS_DELTA_MESSAGES`
- behavior:
  - sync triggers on either byte threshold or message threshold, closer to OpenClaw delta policy.

## Increment 6 Landed
- `gemini async batch state machine`:
  - upload -> create batch -> poll -> download output
  - file: `quentin/memory/embedding_batch.py`
- config/env support:
  - `MEM_EMBED_GEMINI_ASYNC_BATCH`
  - `MEM_EMBED_GEMINI_ASYNC_WAIT`
  - `MEM_EMBED_GEMINI_ASYNC_POLL_S`
  - `MEM_EMBED_GEMINI_ASYNC_TIMEOUT_S`
  - wiring in `quentin/memory/fabric.py`
- parser-level guarantees:
  - preserves input order via `req_{index}` mapping
  - strict error on missing batch output items

## Increment 7 Landed
- `memory status surface` (OpenClaw manager.status parity, partial):
  - `MemoryFabric.stats()` now exposes:
    - store/provider/model
    - batch status (enabled/failures/cache entries/async flags)
    - vector readiness
    - tier counts + total records
  - file: `quentin/memory/fabric.py`
- `observability memory metrics` now include `fabric_status` payload:
  - file: `quentin/observability/service.py`

## Increment 8 Landed
- `manager-search style recall telemetry` in memory traces:
  - `source_counts`, `top_sources`
  - `include_cross_domain` flag
  - hybrid candidate counters: `text_count`, `vec_count`, `fused_count`
  - file: `quentin/memory/fabric.py`
- observability aggregation added:
  - recall `source_counts` rollup
  - candidate averages (`text/vec/fused`)
  - file: `quentin/observability/service.py`

## Increment 9 Landed
- `session-files.ts` parity (Python port):
  - JSONL transcript parser (`user`/`assistant` extraction + text block normalization)
  - full-file session entry builder (`path/mtime/size/hash/content`)
  - file: `quentin/memory/session_files.py`
- `sync-session-files` incremental capability (offset-based):
  - consume only complete appended JSONL lines
  - ignores trailing partial line until completed
  - file: `quentin/memory/session_files.py`
- `MemoryFabric` session transcript delta API:
  - `sync_session_file_delta(file_path, ...)`
  - tracks per-file offset in-process and writes only new transcript messages into memory
  - file: `quentin/memory/fabric.py`

## Increment 10 Landed
- `DirtySync -> MemoryFabric` real callback wiring:
  - new callback builder `build_memory_sync_callback(...)`
  - extracts transcript JSONL paths from dirty delta payload
  - calls `MemoryFabric.sync_session_file_delta(...)` for offset-based incremental indexing
  - file: `quentin/infra/sessions/dirty_sync.py`
- loop bootstrap integration:
  - `initialize_loop(...)` now binds global `dirty_sync.sync_callback` to current loop memory fabric
  - file: `quentin/cognitive/loop_maintenance.py`

## Increment 11 Landed
- `manager.embedding-batches` dynamic flow-control parity:
  - tier-aware batch concurrency policy (`tier 1 -> conservative`, `tier 5 -> 100`)
  - env wiring:
    - `MEM_EMBED_ACCOUNT_TIER`
    - `MEM_EMBED_BATCH_CONCURRENCY` (upper-bounds/floor-adjusted by tier policy)
  - files:
    - `quentin/memory/embedding_batch.py`
    - `quentin/memory/fabric.py`
- `openai-batch` protocol isolation:
  - upload/create/poll/download moved to dedicated protocol helper
  - file: `quentin/memory/openai_batch_protocol.py`

## Increment 12 Landed
- `internal.ts`-style function fingerprint foundation:
  - per-function hashing for Python and JS/TS-like sources
  - fingerprint metadata injected into `remember_file` records
  - files:
    - `quentin/memory/code_fingerprint.py`
    - `quentin/memory/fabric.py`

## Increment 13 Landed
- function-level dedupe gate (position-insensitive):
  - fingerprint hash now supports location-insensitive mode (function move/reorder does not change hash)
  - `remember_file(...)` now skips reindex/re-embedding when function fingerprint hash unchanged
  - persisted cache table: `file_fingerprint_cache(file_path, function_hash, updated_at)`
  - files:
    - `quentin/memory/code_fingerprint.py`
    - `quentin/memory/fabric.py`

## Increment 14 Landed
- `sync-memory-files.ts` style workspace sync (initial parity):
  - new `MemoryFabric.sync_memory_files(...)`
  - capabilities:
    - scan `MEMORY.md` / `memory.md` / `memory/**/*.md`
    - force vs dirty-files selective indexing
    - content-hash cache for unchanged skip
    - stale file cleanup (remove deleted file records)
    - progress callback fields (`completed`, `total`, optional `label`)
  - source isolation:
    - sync path writes under `memory_file:` source prefix to support safe stale cleanup
  - file: `quentin/memory/fabric.py`

## Increment 15 Landed
- `search-manager.ts` / `manager-search.ts` parity (incremental):
  - added parallel cross-session recall scheduler + RRF fusion
  - new module:
    - `quentin/memory/search_manager.py`
  - `MemoryFabric` integration:
    - new `recall_across_sessions(...)`
    - emits `recall_across_sessions` trace payload with session hit stats
  - file:
    - `quentin/memory/fabric.py`

## Increment 16 Landed
- cross-session search flow-control hardening:
  - new `SearchManagerConfig`:
    - `max_workers`
    - `per_session_timeout_s`
  - per-session timeout + error isolation:
    - one slow/failing session no longer blocks whole cross-session query
    - result includes `errors` and `timed_out_sessions`
  - files:
    - `quentin/memory/search_manager.py`
    - `quentin/memory/fabric.py`
- `MemoryFabric` env wiring:
  - `QUENTIN_MEMORY_SEARCH_CONCURRENCY`
  - `QUENTIN_MEMORY_SEARCH_TIMEOUT_S`

## Increment 17 Landed
- memory status observability extension:
  - `MemoryFabric.stats()` now exposes search scheduler status:
    - `search.max_workers`
    - `search.per_session_timeout_s`
  - file:
    - `quentin/memory/fabric.py`

## Increment 18 Landed
- async cross-session search entry (manager-search parity extension):
  - `ParallelSearchManager.search_across_sessions_async(...)`
    - per-session timeout via `asyncio.wait_for`
    - optional `cancel_event` cancellation gate
    - optional `overall_timeout_s` budget
    - result fields: `cancelled`, `cancelled_sessions`
  - `MemoryFabric.recall_across_sessions_async(...)`
    - env support: `QUENTIN_MEMORY_SEARCH_OVERALL_TIMEOUT_S`
    - async trace event: `recall_across_sessions_async`
  - files:
    - `quentin/memory/search_manager.py`
    - `quentin/memory/fabric.py`

## Increment 19 Landed
- `memory.recall` tool path activated (from stub -> production handler):
  - supports:
    - single-session recall
    - cross-session recall (sync)
    - cross-session recall (async, with timeout parameter pass-through)
  - structured output:
    - `records`, `count`, `session_hits`, `errors`, `timed_out_sessions`, `cancelled_sessions`
  - files:
    - `quentin/tools/packs/memory_pack.py`
    - `tests/unit/test_memory_pack.py`

## Increment 20 Landed
- tool-layer cancellation bridge for async cross-session search:
  - `memory.recall` now forwards `ToolCallContext.cancel_token` into async recall cancel event
  - enables top-layer cancellation to stop cross-session async search path
  - files:
    - `quentin/tools/packs/memory_pack.py`
    - `tests/unit/test_memory_pack.py`

## Increment 21 Landed
- cross-session search priority scheduling:
  - `SessionSearchSpec` adds `priority`
  - scheduler order now: `priority` desc, then `weight` desc
  - result adds `scheduled_sessions` for observability
  - files:
    - `quentin/memory/search_manager.py`
    - `quentin/memory/fabric.py`
- tool passthrough for per-session scheduling policy:
  - `memory.recall` accepts `session_options`
  - forwards `priority/weight/top_k_override` to cross-session recall
  - file:
    - `quentin/tools/packs/memory_pack.py`

## Increment 22 Landed
- unified runtime tuning (P1 config convergence):
  - new runtime config object:
    - `quentin/config/memory_runtime.py`
  - profile support:
    - `safe` / `balanced` / `aggressive`
  - unified knobs wired to memory fabric/search/sync:
    - search concurrency/timeouts
    - sync concurrency
    - rerank enable + priors + half-life
  - dirty sync runtime tuning integrated in loop init:
    - `dirty_sync.configure(debounce_sec, dedupe_ttl_sec)`
  - files:
    - `quentin/config/memory_runtime.py`
    - `quentin/memory/fabric.py`
    - `quentin/infra/sessions/dirty_sync.py`
    - `quentin/cognitive/loop_maintenance.py`

## Increment 23 Landed
- embedding retry strategy matrix (P1):
  - batch HTTP retry/backoff generalized for OpenAI/Gemini sync batch path
  - config knobs:
    - `MEM_EMBED_RETRY_MAX_ATTEMPTS`
    - `MEM_EMBED_RETRY_BASE_DELAY_MS`
    - `MEM_EMBED_RETRY_MAX_DELAY_MS`
  - batch status now reports retry config
  - file:
    - `quentin/memory/embedding_batch.py`
    - `quentin/memory/fabric.py`

## Increment 24 Landed
- rerank pipeline + observability extension (P2):
  - search rerank stage with:
    - source priors
    - time decay
    - domain match bonus
  - cross-session results include `rerank_applied`
  - observability now tracks cross-session recall counters:
    - sync/async calls
    - timeout counts
    - cancellation counts
  - function fingerprint precision uplift:
    - Python class method qualname + semantic AST fingerprint
    - JS/TS block-level function/method extraction
  - files:
    - `quentin/memory/search_manager.py`
    - `quentin/observability/service.py`
    - `quentin/memory/code_fingerprint.py`

## Increment 25 Landed
- manager lifecycle orchestrator (`manager.ts` parity core):
  - new orchestrator module:
    - `quentin/memory/manager.py`
  - integrated in loop bootstrap:
    - `quentin/cognitive/loop_maintenance.py`
  - capabilities:
    - startup/session-start sync
    - pre-search sync gate
    - periodic background sync + status surface
- async batch persistence + resume hardening:
  - persistent job table + restart resume:
    - `quentin/memory/embedding_batch.py` (`BatchJobStore`)
  - resumed job counters exposed in batch status
- provider failure taxonomy + counters:
  - retryable/non-retryable error classes
  - counters:
    - `retry_attempts_total`
    - `fallback_calls_total`
    - `resumed_jobs_total`
  - file:
    - `quentin/memory/embedding_batch.py`
- search budget controls landed:
  - `max_sessions_scanned`
  - `max_candidates_reranked`
  - files:
    - `quentin/memory/search_manager.py`
    - `quentin/config/memory_runtime.py`
    - `quentin/memory/fabric.py`
- observability detail upgrade:
  - recall latency percentiles (`p50` / `p95`)
  - embedding batch counters surfaced in overview
  - file:
    - `quentin/observability/service.py`

## Increment 26 Landed
- provider fallback matrix completion (residual closure):
  - explicit `ProviderDisabledBatchError` path
  - non-retryable HTTP (e.g. auth/schema) routed to non-retryable taxonomy
  - provider-disabled events now disable batch path immediately
  - file:
    - `quentin/memory/embedding_batch.py`
- high-level recall hook deep wiring:
  - `MemoryFabric.recall(..., pre_search_sync=...)` added
  - cross-session scheduler calls child recall with `pre_search_sync=False` to avoid repeated sync storms
  - loop bootstrap binds manager hook into memory fabric:
    - `set_pre_search_sync_hook(memory_manager.maybe_sync_before_search)`
  - files:
    - `quentin/memory/fabric.py`
    - `quentin/memory/search_manager.py`
    - `quentin/cognitive/loop_maintenance.py`
- timeout-pressure adaptive degradation:
  - session fanout auto-cap under pressure
  - rerank auto-downshift when timeout ratio exceeds threshold
  - budget payload includes:
    - `adaptive_degrade_applied`
    - `timeout_pressure`
  - file:
    - `quentin/memory/search_manager.py`

## Increment 27 Landed
- observability auth/recover hints:
  - add `embedding_batch_hints` based on provider + batch counters + failure rate
  - includes actionable diagnostics for:
    - provider disabled/auth mismatch
    - fallback spike
    - retry pressure
  - file:
    - `quentin/observability/service.py`
- loop-level manager hook integration test (transcript path):
  - verifies `initialize_loop` wires `set_pre_search_sync_hook(memory_manager.maybe_sync_before_search)`
  - verifies session-start + pre-search hook path drives:
    - `sync_memory_files`
    - `sync_session_file_delta`
  - file:
    - `tests/unit/test_loop_maintenance_memory_hook.py`

## Increment 28 Landed
- observability schema contract hardening:
  - added memory overview key-contract test (golden-style schema stability guard)
  - file:
    - `tests/unit/test_observability_memory_metrics.py`

## Increment 29 Landed
- chaos-style async batch resume integration:
  - restart resume happy-path test (reuse old job id without re-upload/re-create)
  - resume-failure recovery test (fallback to new upload/create and complete)
  - file:
    - `tests/integration/test_memory_batch_resume_chaos.py`
- adaptive-degrade runtime config exposure:
  - new env knobs:
    - `QUENTIN_MEMORY_SEARCH_ADAPTIVE_DEGRADE_ENABLE`
    - `QUENTIN_MEMORY_SEARCH_TIMEOUT_PRESSURE_THRESHOLD`
    - `QUENTIN_MEMORY_SEARCH_ADAPTIVE_SESSION_CAP_FACTOR`
  - wired from runtime config into search manager
  - files:
    - `quentin/config/memory_runtime.py`
    - `quentin/memory/fabric.py`
    - `tests/unit/test_memory_runtime_config.py`
- adaptive-degrade tuning guide:
  - workload-based env preset recommendations (small/medium/large)
  - file:
    - `docs/improve/memory_adaptive_degrade_tuning.md`

## Increment 30 Landed
- multi-provider chaos resume coverage:
  - Gemini async resume after restart (reuse old job id, no resubmit)
  - Gemini resume-failure recovery (auto resubmit and complete)
  - file:
    - `tests/integration/test_memory_batch_resume_chaos.py`

## Increment 31 Landed
- high-fanout adaptive-degrade benchmark test:
  - synthetic 100+ session fanout validates:
    - adaptive session cap
    - timeout-pressure signaling
    - rerank downshift under pressure
  - file:
    - `tests/integration/test_memory_adaptive_degrade_benchmark.py`
- timeout threshold bugfix:
  - `timeout_pressure_threshold=0.0` now works correctly (no accidental fallback to `0.4`)
  - files:
    - `quentin/memory/search_manager.py`
    - `tests/unit/test_memory_search_manager.py`

## Increment 32 Landed
- performance fallback acceleration:
  - SQLite client-scan vector search now supports optional NumPy vectorized cosine scoring.
  - fallback remains pure Python when NumPy is unavailable.
  - file:
    - `quentin/memory/store_sqlite.py`
- performance observability visibility:
  - `MemoryFabric.stats()` now includes:
    - `vector.backend` (`sqlite_vec` | `client_scan`)
    - `vector.math_backend` (`numpy` | `python` | `unknown`)
  - observability overview adds:
    - `memory_performance_hints`
  - files:
    - `quentin/memory/fabric.py`
    - `quentin/observability/service.py`
    - `tests/unit/test_memory_embedding_batch.py`
    - `tests/unit/test_observability_memory_metrics.py`

## Increment 33 Landed
- corpus-tier benchmark + SLO enforcement:
  - `bench_memory_recall.py` now supports:
    - `--slo-file`
    - `--fail-on-slo`
  - SLO rule evaluation checks p95/avg latency and hit@k thresholds per mode and tier.
  - files:
    - `scripts/bench_memory_recall.py`
    - `config/memory_recall_slo.json` (10k/100k/1M default tiers)
    - `tests/integration/test_bench_memory_recall_slo_runs.py`

## Increment 34 Landed
- hybrid recall quality hardening:
  - add keyword-anchor preservation in hybrid fusion path
  - env knob: `QUENTIN_MEMORY_HYBRID_KEYWORD_ANCHOR_TOPN` (default `1`)
  - file:
    - `quentin/memory/fabric.py`
- benchmark diagnostics hardening:
  - benchmark output now includes:
    - `store`, `vector_backend`, `vector_math_backend`
    - ingest throughput (`ingest_records_per_sec`)
  - benchmark emits issue events for:
    - `vector_backend_client_scan`
    - `vector_math_python`
    - `hybrid_keyword_starvation`
  - file:
    - `scripts/bench_memory_recall.py`
- coverage:
  - `tests/unit/test_memory_hybrid_recall.py`

## Increment 35 Landed
- SQLite fallback vector path optimization:
  - implemented two-phase fetch strategy for client-scan vector search:
    - phase 1: scan `id, vector` and compute top-k scores
    - phase 2: hydrate full rows for top-k ids only
  - feature flag:
    - `QUENTIN_MEMORY_VECTOR_TWO_PHASE_FETCH` (`1` default, `0` fallback to legacy single-phase)
  - files:
    - `quentin/memory/store_sqlite.py`
    - `tests/unit/test_memory_store_sqlite.py`
- memory status visibility:
  - `vector.fetch_strategy` added to `MemoryFabric.stats()`
  - benchmark output includes `vector_fetch_strategy`
  - files:
    - `quentin/memory/fabric.py`
    - `scripts/bench_memory_recall.py`
- measured outcome (local 10k / sqlite client-scan):
  - vector/hybrid latency improved from ~700ms class to ~520ms class
  - quality remains:
    - `hybrid hit@k = 1.0`
    - `hybrid hit_text@k = 1.0`

## Increment 36 Landed
- sqlite-vec activation guard in benchmark:
  - new flag: `--require-index-backend`
  - when `--backend sqlite_vec` is requested but actual backend is fallback (`client_scan`), benchmark now:
    - emits `sqlite_vec_not_active` issue
    - exits with code `3` if guard is enabled
  - files:
    - `scripts/bench_memory_recall.py`
    - `tests/integration/test_bench_memory_recall_index_backend_guard.py`
- measured checkpoint (local 10k, current env without sqlite-vec extension):
  - backend remains `client_scan` (guard confirms)
  - vector/hybrid latency around ~450-600ms class
  - quality:
    - `vector hit@k = 1.0`
    - `hybrid hit@k = 1.0`, `hybrid hit_text@k = 1.0`

## Increment 37 Landed
- SLO rebaseline automation:
  - new script: `scripts/rebaseline_memory_slo.py`
  - builds `memory_recall_slo` from benchmark JSONL with backend filters:
    - `--backend`
    - `--vector-backend`
  - reliability gates:
    - `--fail-on-empty` exits with code `4` if no tiers are generated
  - files:
    - `scripts/rebaseline_memory_slo.py`
    - `tests/integration/test_rebaseline_memory_slo_runs.py`
    - `docs/memory_sqlite_vec.md`

## Increment 38 Landed
- one-shot SLO rollout pipeline:
  - new script: `scripts/run_memory_slo_pipeline.py`
  - stages:
    - benchmark
    - index-backend guard (optional)
    - SLO generation (`rebaseline_memory_slo.py`)
    - optional apply to target SLO file
  - file:
    - `scripts/run_memory_slo_pipeline.py`
    - `tests/integration/test_run_memory_slo_pipeline_runs.py`
    - `docs/memory_sqlite_vec.md`

## Increment 39 Landed
- sqlite-vec environment readiness precheck:
  - new script: `scripts/check_sqlite_vec_env.py`
  - check order:
    - `QUENTIN_SQLITE_VEC_PATH` extension loadability
    - fallback to `sqlite_vec` python module + `loadable_path()`
  - strict mode:
    - `--strict` exits with code `5` when sqlite-vec is not ready
  - files:
    - `scripts/check_sqlite_vec_env.py`
    - `tests/integration/test_check_sqlite_vec_env_runs.py`
- pipeline integration:
  - `run_memory_slo_pipeline.py` now runs precheck automatically when `--backend sqlite_vec`
  - can be bypassed explicitly with `--skip-precheck`
  - file:
    - `scripts/run_memory_slo_pipeline.py`

## Increment 40 Landed
- intelligence-first memory benchmark rollout:
  - new benchmark script:
    - `scripts/bench_memory_intelligence.py`
  - core intelligence metrics:
    - `task_success_rate`
    - `first_hit_useful_rate`
    - `error_recurrence_rate`
    - `memory_pollution_rate`
    - `intelligence_score` (weighted trend metric)
  - diagnostics now emit explicit weak-signal issues:
    - `task_success_low`
    - `first_hit_useful_low`
    - `error_recurrence_high`
    - `memory_pollution_high`
  - one-shot pipeline:
    - `scripts/run_memory_intelligence_pipeline.py`
  - config and governance:
    - `config/memory_intelligence_slo.json`
  - docs:
    - `docs/bench_memory_intelligence.md`
  - integration coverage:
    - `tests/integration/test_bench_memory_intelligence_runs.py`
    - `tests/integration/test_run_memory_intelligence_pipeline_runs.py`

## Increment 41 Landed
- anti-pollution recall hardening:
  - unified domain policy filter across all recall modes:
    - `text_only`
    - `vector_only`
    - `hybrid`
    - default branch
  - file:
    - `quentin/memory/fabric.py`
  - unit coverage:
    - `tests/unit/test_cross_domain_memory.py`
- intelligence benchmark hardening:
  - ensure domain is persisted in records (`record.domain`) during corpus build
  - add query difficulty profile:
    - `--case-profile basic|mixed` (default `mixed`)
  - add query domain policy knob:
    - `--query-domain-policy none|case` (default `case`)
  - files:
    - `scripts/bench_memory_intelligence.py`
    - `scripts/run_memory_intelligence_pipeline.py`
    - `docs/bench_memory_intelligence.md`

## Increment 42 Landed
- text-only intelligence uplift (lexical AND matching):
  - SQLite text search now tokenizes query and applies order-insensitive `LIKE` AND matching.
  - improves semantic-ish text recall where wording order differs.
  - file:
    - `quentin/memory/store_sqlite.py`
  - unit coverage:
    - `tests/unit/test_memory_store_sqlite.py`
- intelligence benchmark quality hardening:
  - mixed profile semantic queries now include unique case-id anchor to reduce ambiguity.
  - correction replay now injects semantic query text for effective post-failure learning checks.
  - `error_recurrence_rate` now measures repeated top-k task failure (not top1 quality, which is tracked by `first_hit_useful_rate`).
  - file:
    - `scripts/bench_memory_intelligence.py`
- measured checkpoint (sqlite / n=300 / mixed profile):
  - `text_only`: task success `1.0`, first-hit useful `0.833`, recurrence `0.0`
  - `hybrid`: task success `1.0`, first-hit useful `0.833`, recurrence `0.0`

## Increment 43 Landed
- first-hit quality uplift:
  - add query-alignment rerank in memory finalize path for `text_only` / `hybrid` (vector-only unchanged).
  - file:
    - `quentin/memory/fabric.py`
- lexical precision hardening:
  - SQLite token search now applies boundary-safe token filtering to avoid numeric substring false hits (`10` vs `210`).
  - broad candidate fetch + Python exact token-boundary filter.
  - file:
    - `quentin/memory/store_sqlite.py`
  - unit coverage:
    - `tests/unit/test_memory_store_sqlite.py`
    - `tests/unit/test_memory_hybrid_recall.py`
- measured checkpoint (sqlite / n=300 / mixed profile):
  - `text_only`: task success `1.0`, first-hit useful `1.0`, recurrence `0.0`
  - `hybrid`: task success `1.0`, first-hit useful `1.0`, recurrence `0.0`

## Increment 44 Landed
- scale-run reliability tooling:
  - add matrix runner with per-tier timeout and machine-readable summary:
    - `scripts/run_memory_intelligence_scale_matrix.py`
  - outputs:
    - `/tmp/memory_intelligence_scale/bench_n<k>.jsonl`
    - `/tmp/memory_intelligence_scale/scale_summary.json`
  - integration coverage:
    - `tests/integration/test_run_memory_intelligence_scale_matrix_runs.py`
- measured checkpoint (venv + sqlite_vec / n=10000 / mixed profile / all modes):
  - `text_only`: task success `1.0`, first-hit useful `1.0`, recurrence `0.0`, pollution `0.0`
  - `vector_only`: task success `1.0`, first-hit useful `1.0`, recurrence `0.0`, pollution `0.0`
  - `hybrid`: task success `1.0`, first-hit useful `1.0`, recurrence `0.0`, pollution `0.0`

## Increment 45 Landed
- scale benchmark contention guard:
  - add exclusive lock for scale matrix runner to avoid concurrent benchmark interference:
    - `--lock-file`
    - `--lock-timeout-s`
  - lock busy exits with code `9`.
  - file:
    - `scripts/run_memory_intelligence_scale_matrix.py`
  - integration coverage:
    - `tests/integration/test_run_memory_intelligence_scale_matrix_runs.py`
- measured scale checkpoints (venv + sqlite_vec / hybrid / mixed profile):
  - `n=30000`: pass, `avg_ms ~67.9`, `p95_ms ~90.6`, intelligence metrics all `1.0/0.0`.
  - `n=100000` (isolated run): pass, `avg_ms ~277.3`, `p95_ms ~358.1`, intelligence metrics all `1.0/0.0`.
  - `n=100000` (concurrent overlapping long-runs observed): p95 spike (`~10695ms`) and latency SLO fail, while intelligence quality remains `1.0`.

## Increment 46 Landed
- 1M-scale intelligence verification (isolated, locked run):
  - runner:
    - `scripts/run_memory_intelligence_scale_matrix.py`
  - output:
    - `/tmp/memory_intelligence_scale5/bench_n1000000.jsonl`
    - `/tmp/memory_intelligence_scale5/scale_summary.json`
  - objective quality at 1M:
    - `task_success_rate = 1.0`
    - `first_hit_useful_rate = 1.0`
    - `error_recurrence_rate = 0.0`
    - `memory_pollution_rate = 0.0`
  - latency at 1M (`hybrid`, sqlite_vec):
    - `avg_ms ~20502`
    - `p95_ms ~21678`
  - conclusion:
    - intelligence quality remains strong at 1M
    - latency SLO is not acceptable at 1M for online path (return code `2` due to `p95_ms` violation)

## Increment 47 Landed
- hybrid online latency optimization (phase-1):
  - fix lexical scoring tokenizer bug:
    - `_score_text` now uses `r\"\\W+\"` split instead of escaped literal pattern.
  - add hybrid fast path:
    - vector-seeded candidate pool first
    - local lexical scoring over seeded candidates
    - guarded fallback to full text search when seeded hits are insufficient
  - new knobs:
    - `QUENTIN_MEMORY_HYBRID_FAST_VECTOR_SEED` (default on)
    - `QUENTIN_MEMORY_HYBRID_VECTOR_SEED_TOPK` (default 200)
    - `QUENTIN_MEMORY_HYBRID_FAST_FALLBACK_ENABLE` (default on)
    - `QUENTIN_MEMORY_HYBRID_FAST_FALLBACK_MIN_HITS` (default 1)
  - debug payload additions:
    - `hybrid_fast_path_used`
    - `hybrid_fast_fallback_used`
    - `hybrid_seed_candidates`
    - `hybrid_text_seed_hits`
  - files:
    - `quentin/memory/fabric.py`
    - `tests/unit/test_memory_hybrid_recall.py`
- measured checkpoint (venv + sqlite_vec / n=100000 / hybrid / mixed):
  - previous isolated reference: `avg_ms ~277.3`, `p95_ms ~358.1`
  - after phase-1 optimization: `avg_ms ~245.4`, `p95_ms ~294.2`
  - quality remains stable at `1.0 / 1.0 / 0.0 / 0.0`

## Increment 48 Landed
- text retrieval efficiency upgrades:
  - online text search now prefers FTS when available and corpus exceeds threshold.
  - compatibility fallback preserved: FTS miss falls back to LIKE path.
  - files:
    - `quentin/memory/fabric.py`
    - `quentin/memory/store_sqlite.py`
- write-path cost control:
  - recall writeback gating:
    - `QUENTIN_MEMORY_RECALL_WRITEBACK_ENABLE` (default on)
    - `QUENTIN_MEMORY_RECALL_WRITEBACK_MAX_UPDATES` (default 20)
  - files:
    - `quentin/memory/fabric.py`
- tiered serving policy:
  - online/offline threshold + active window policy:
    - `QUENTIN_MEMORY_ONLINE_OFFLINE_THRESHOLD` (default `300000`)
    - `QUENTIN_MEMORY_ONLINE_ACTIVE_WINDOW_ENABLE` (default on)
    - `QUENTIN_MEMORY_ONLINE_ACTIVE_WINDOW_DAYS` (default `90`)
  - files:
    - `quentin/memory/fabric.py`
- observability/health:
  - large corpus without FTS/sqlite-vec warning in fabric status + memory performance hints.
  - file:
    - `quentin/observability/service.py`
- tests:
  - `tests/unit/test_memory_hybrid_recall.py`
  - `tests/unit/test_observability_memory_metrics.py`
- measured checkpoints:
  - `100k hybrid` (isolated, sqlite_vec, mixed, n_cases=10):
    - `avg_ms ~260.3`, `p95_ms ~349.7`, quality `1.0/1.0/0.0/0.0`
  - `1M low-case smoke` (existing 1M corpus):
    - sampled hit rate `0.75` (3/4 probes) with no broad quality collapse observed.

## Increment 49 Landed
- recall write-path micro-optimization:
  - replace per-record full `update()` in recall finalize path with batched `touch_access_many()`.
  - avoids vector upsert work on access-only updates and reduces commit amplification.
  - files:
    - `quentin/memory/store_base.py`
    - `quentin/memory/store_sqlite.py`
    - `quentin/memory/store_postgres.py`
    - `quentin/memory/fabric.py`
  - tests:
    - `tests/unit/test_memory_store_sqlite.py`
    - `tests/unit/test_memory_hybrid_recall.py`
- measured note:
  - 100k hybrid latency remains stable in the ~300-400ms p95 band across isolated runs (machine/load-sensitive variance still visible).
  - quality remains stable at `1.0 / 1.0 / 0.0 / 0.0`.
