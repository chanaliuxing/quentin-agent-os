# OpenClaw Memory Gap TODO (Execution List)

## Scope
Remaining parity work after Increment 25.  
Priority legend: `P0` block-level parity, `P1` high leverage, `P2` optimization.

## P0 (Must Land Next)
- [x] Manager lifecycle orchestrator (`manager.ts` parity core)
  - target: `quentin/memory/manager.py` (new)
  - deliver:
    - startup sync strategy (`on_session_start`)
    - pre-search sync gate (`on_search`)
    - periodic background sync (`interval`)
    - unified status + health report
  - acceptance:
    - manager can drive `sync_memory_files` + `sync_session_file_delta` without loop-side custom wiring
    - one API call returns lifecycle state + last sync results

- [x] Async batch job persistence + resume (`openai-batch.ts` recovery parity)
  - target:
    - `quentin/memory/openai_batch_protocol.py`
    - `quentin/memory/embedding_batch.py`
    - `data` sqlite metadata table (new)
  - deliver:
    - pending/running/completed/failed persisted states
    - process restart resumes polling unfinished jobs
  - acceptance:
    - interrupted run can continue and complete without re-submitting identical requests

## P1 (High Priority)
- [x] Provider-specific failure taxonomy expansion
  - target: `quentin/memory/embedding_batch.py`
  - deliver:
    - explicit classes for retryable/non-retryable/provider-disabled errors
    - fallback trigger matrix per provider
  - acceptance:
    - unit tests cover 429/5xx/network/schema/auth failures with expected path (retry/fallback/disable)

- [x] Session sync payload schema normalization
  - target:
    - `quentin/infra/sessions/dirty_sync.py`
    - `quentin/memory/session_files.py`
  - deliver:
    - canonical delta schema contract
    - strict validation + metrics for dropped malformed payloads
  - acceptance:
    - malformed delta does not crash, produces explicit diagnostics

- [x] Function fingerprint language coverage
  - target: `quentin/memory/code_fingerprint.py`
  - deliver:
    - TS class method + exported function edge cases
    - decorator/annotation normalization policy docs
  - acceptance:
    - move-only refactors keep same fingerprint in regression fixtures

## P2 (Optimization / Quality)
- [x] Search scheduler budget policies
  - target:
    - `quentin/memory/search_manager.py`
    - `quentin/memory/fabric.py`
  - deliver:
    - per-query budget caps (max sessions scanned, max candidates reranked)
    - adaptive degradation when timeout pressure high
  - acceptance:
    - load test shows bounded latency under session fanout spikes

- [x] Rerank policy configuration surface
  - target:
    - `quentin/config/memory_runtime.py`
    - docs
  - deliver:
    - declarative per-domain rerank presets (code/chat/research)
  - acceptance:
    - one env/profile switch changes rerank behavior predictably

- [x] Observability detail upgrade
  - target: `quentin/observability/service.py`
  - deliver:
    - percentile latency (p50/p95) for recall and cross-session recall
    - retry/fallback counters for embedding batch pipeline
  - acceptance:
    - dashboard exports these fields stably from JSON overview

## Residual Gap (Post-P2)
- [x] Provider-specific fallback matrix completeness
  - add stricter auth/schema/provider-disabled error branches and regression fixtures.
- [x] Runtime memory manager deeper integration
  - wire `MemoryManager` pre-search/session hooks directly in all high-level recall entrypoints.
- [x] Cross-session adaptive degradation
  - add timeout-pressure auto downshift for rerank/session fanout.

## Verification Checklist
- [x] Unit tests for each new module/path
- [x] Regression run:
  - `pytest tests/unit -q` (or focused subsets during incremental landings)
- [x] Compile check for touched modules
- [x] Update `docs/improve/openclaw_memory_incremental_port.md` with each increment

## Next Candidate Backlog (Optional)
- [x] Embed provider-specific auth/recover hints into observability overview payload.
- [x] Add integration tests for loop-level manager hook under real session transcripts.

## Current Gap Analysis (Post Increment 27)
- structural parity gap:
  - effectively closed for current OpenClaw memory scope (manager/batching/sync/search/observability core paths).
- residual risk (non-blocking):
  - runtime behavior under real provider turbulence still depends on production telemetry volume.
  - cross-process restart semantics validated at unit level; multi-process chaos regression can still be strengthened.

## New TODO (Hardening Track)
- [x] Add chaos-style integration tests for async batch resume across process boundaries.
- [x] Add memory observability snapshot golden tests (stable schema contract).
- [x] Add adaptive-degrade tuning guide with recommended env presets by workload size.

## Current Residual Gap
- [x] Multi-provider chaos coverage expansion
  - OpenAI + Gemini async resume chaos parity both covered.
- [x] End-to-end benchmark under synthetic high fanout
  - add repeatable benchmark to validate adaptive cap + timeout-pressure behavior at 100+ session specs.

## Current Gap Status
- functional parity: closed for current OpenClaw memory migration scope.
- hardening parity: closed for currently defined backlog items.

## Performance Gap TODO
- [x] Add vector math acceleration path for client-scan fallback.
  - landed: optional NumPy vectorized cosine scoring in SQLite fallback search.
- [x] Expose vector backend visibility in memory status/observability.
  - landed: `vector.backend` and `vector.math_backend` in `MemoryFabric.stats()`.
- [x] Emit performance hints when large-scale recall uses client-scan fallback.
  - landed: `memory_performance_hints` in observability overview.
- [x] Add benchmark with real corpus size tiers (10k/100k/1M) and latency SLO targets.
  - landed: `scripts/bench_memory_recall.py --slo-file --fail-on-slo` + `config/memory_recall_slo.json`.

## Final Gap Status
- OpenClaw memory migration scope: completed (feature + hardening + performance instrumentation/baselines).

## Post-Benchmark TODO
- [ ] Enable indexed vector backend in runtime environments (`sqlite-vec`/`pgvector`) to remove client-scan bottleneck.
- [x] Optimize SQLite fallback vector path with two-phase fetch (score IDs first, hydrate top_k only).
- [ ] Re-baseline SLO thresholds after indexed backend rollout.
- [x] Add benchmark guard to fail when requested indexed backend is not active.
  - landed: `bench_memory_recall.py --require-index-backend`.
- [x] Add automated SLO generation from benchmark artifacts.
  - landed: `scripts/rebaseline_memory_slo.py` with backend filters and empty-output guard.
- [x] Add one-shot rollout pipeline for benchmark + guard + SLO generation.
  - landed: `scripts/run_memory_slo_pipeline.py`.
- [x] Add sqlite-vec environment readiness precheck before pipeline benchmark stage.
  - landed: `scripts/check_sqlite_vec_env.py` + pipeline auto-precheck (`--skip-precheck` to bypass).
- [x] Add intelligence-first benchmark that prioritizes smart task outcomes over pure latency.
  - landed: `scripts/bench_memory_intelligence.py` with task-success / first-hit / recurrence / pollution metrics.
- [x] Add intelligence benchmark pipeline for repeatable execution.
  - landed: `scripts/run_memory_intelligence_pipeline.py`.
- [x] Add intelligence scoring governance config.
  - landed: `config/memory_intelligence_slo.json`.
- [x] Reduce cross-domain pollution by applying domain policy across all recall modes.
  - landed: `quentin/memory/fabric.py` + unit coverage in `tests/unit/test_cross_domain_memory.py`.
- [x] Prevent intelligence benchmark score inflation with mixed-difficulty cases.
  - landed: `scripts/bench_memory_intelligence.py --case-profile mixed` (exact + semantic queries).
- [x] Improve text-only semantic robustness (order-insensitive lexical recall).
  - landed: token-AND text matching in `quentin/memory/store_sqlite.py`.
- [x] Make recurrence metric represent true task failure recurrence (top-k), not top1 ranking quality.
  - landed: `scripts/bench_memory_intelligence.py` metric refinement.
- [x] Raise first-hit usefulness for mixed-profile tasks.
  - landed: query-alignment rerank (`quentin/memory/fabric.py`) + boundary-safe token filtering (`quentin/memory/store_sqlite.py`).
- [x] Add tiered scale benchmark runner with timeout and summary artifacts.
  - landed: `scripts/run_memory_intelligence_scale_matrix.py`.
- [x] Guard scale benchmark against concurrent-run latency contamination.
  - landed: matrix runner lock (`--lock-file`, `--lock-timeout-s`, exit code `9` on busy).

## 1M Scale Decision
- [x] Validate intelligence-quality stability at 1M scale.
  - result: quality metrics stable (`task_success=1.0`, `first_hit=1.0`, `recurrence=0`, `pollution=0`).
- [ ] Close 1M online latency gap (current `hybrid p95` around `21.7s` in sqlite_vec run).
  - action: treat 1M as offline evaluation tier until retrieval/index strategy is upgraded for online SLO.
  - progress: phase-1 hybrid fast-path reduced 100k isolated hybrid `p95` from `~358ms` to `~294ms` with no quality regression.
- [x] Land P1/P2 online-latency controls (FTS preference, writeback gating, active-window policy).
  - landed in `quentin/memory/fabric.py` + `quentin/observability/service.py` with unit coverage.
