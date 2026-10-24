# Session Model Incremental Port (OpenClaw-style)

## Goal
将会话生命周期、历史裁剪/压缩、并发 lane/lock/abort、delta 脏同步统一到 `SessionState` 模型，避免上层散落逻辑。

## What is landed

- `quentin/infra/sessions/session_store.py`
- Added `SessionState` / `SessionCompactionState` / `SessionStore` / `SessionPolicy`
- Added persistent state file per session: `data/runtime/sessions/<session>.json`
- Added deterministic `maybe_compact()` with policy thresholds and gist injection
- Added optimistic version guard (`expected_version`) and atomic save (`.tmp -> replace`)

## Integration points

- `quentin/cognitive/loop_maintenance.py`
- Loop init now creates `loop.session_store` and `loop.session_policy`
- `SessionDeltaWriter` now receives `session_store`

- `quentin/memory/session_deltas.py`
- Writes pending byte/message/event counters into `SessionState.deltas_cursor`
- Writes latest attempt metadata into `SessionState.metadata`
- Pushes `session_state_path` and `session_state_version` into `dirty_sync.track_change`
- Resets cursors and dirty flag after successful memory write

- `quentin/infra/concurrency/lane_orchestrator.py`
- Added `run_in_session(session, ...)`
- Lane key and abort signal are read from session state (`lane_key`, `abort_signal_id`)
- Supports lock attachment via `session_store.acquire_lock(session)`

- `quentin/cognitive/loop_entrypoints.py`
- Async task entry uses session model first
- Appends user turn to `SessionState.history`
- Calls `session_store.maybe_compact()` before executing loop body
- Sync/Async entrypoints both use session model when available
- Falls back to legacy lane path when session model path fails

- `quentin/cognitive/loop_orchestration.py`
- Context overflow branch now prefers `session_store.maybe_compact()` and falls back to legacy memory compactor

- `quentin/runtime/brain_daemon.py`
- `run_once` now binds execution to session model (`run_sync_in_session`)
- Session daemon now owns a `SessionStore` instance, so daemon lane/lock/abort are session-state aligned

## Environment controls

Added in `.env`:

- `QUENTIN_SESSION_STORE_ENABLED`
- `QUENTIN_SESSION_STORE_DIR`
- `QUENTIN_SESSION_HISTORY_MAX_MESSAGES`
- `QUENTIN_SESSION_HISTORY_MAX_CHARS`
- `QUENTIN_SESSION_HISTORY_KEEP_RECENT`
- `QUENTIN_SESSION_COMPACTION_MIN_MESSAGES`
- `QUENTIN_SESSION_COMPACTION_SUMMARY_MAX_CHARS`
- `QUENTIN_PLANNER_CODE_BACKEND`
- `QUENTIN_PLANNER_CODE_FALLBACK`

## Validation checklist

- [x] Same session state can be reloaded after restart
- [x] Compaction is stateful (`compaction_count`, `last_compacted_at`, `last_summary`)
- [x] History trimming is deterministic by policy thresholds
- [x] Lane/abort are driven by session model fields
- [x] Dirty sync + session delta writes back to session state

## Benchmark

- Run:
  - `PYTHONPATH=. python scripts/session_model_benchmark.py`
- Output:
  - `generated/benchmarks/session_model_benchmark_report.json`
- Current check dimensions:
  - session recovery after restart
  - compaction statefulness + predictable trimming
  - lane/abort binding to session state
  - session delta -> session state cursor bridge

## Verify Gate Integration

- `verify_system.py` now includes session-model benchmark audit by default.
- Gate envs:
  - `QUENTIN_VERIFY_SESSION_BENCHMARK=1`
  - `QUENTIN_VERIFY_SESSION_BENCHMARK_MIN_SCORE=0.95`
  - `QUENTIN_VERIFY_SESSION_BENCHMARK_REQUIRE_PASS=1`

## Autoloop Integration

- `scripts/brain_autoloop.py` now runs session benchmark in each iteration (in addition to planning benchmark).
- Config keys:
  - `session_benchmark_command`
  - `session_benchmark_timeout_s`
  - `session_benchmark_report_path`
  - `session_benchmark_min_score`
  - `session_benchmark_require_pass`

## Remaining gap (next)

- Replace legacy direct prompt/history assembly in deeper planner layers with pure `SessionPolicy` outputs
- Add compaction summarizer plugin (LLM summary) with deterministic fallback still enabled
- Add benchmark scenario for session recovery + compaction efficacy + abort responsiveness
