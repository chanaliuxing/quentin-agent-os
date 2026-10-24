# Autonomy TODO: Brain Daemon + Task Queue + PatchFlow

Date: 2026-02-08

Goal:
- Make the "AI brain" run continuously with real governance:
  - Pull tasks from a queue
  - Run CognitiveLoop
  - Run maintenance loops
  - Generate/apply patches with tests and rollback
  - Measure everything (bench + observability)

Principles:
- Default offline (no network) unless explicitly enabled.
- Default no auto-apply in non-sandbox.
- Every new daemon capability ships with an integration test + benchmark script.

## P0: Task Queue (Executable Autonomy)

- [x] File-backed TaskQueue (JSONL) with claim/mark_done
  - File: `quentin/runtime/task_queue.py`
  - Env override: `QUENTIN_TASK_QUEUE_PATH`
  - DoD: queue can be used from CLI and drained deterministically offline.

- [x] BrainDaemon can run from TaskQueue
  - Files: `quentin/runtime/brain_daemon.py`, `scripts/run_brain_daemon.py`
  - DoD: `python scripts/run_brain_daemon.py --from-queue --max-tasks 2` works with `LLM_STUB=1`.

- [x] CLI commands for queue
  - File: `quentin/cli/qctl.py`
  - Commands: `task-enqueue`, `task-run-queue`
  - DoD: integration test enqueues 2 tasks and drains them.

- [x] Offline benchmark for task queue throughput
  - File: `scripts/bench_task_queue_offline.py`
  - Output: `data/bench/task_queue_offline.json` (ignored)
  - DoD: script runs with `LLM_STUB=1` and reports tasks/sec.

## P1: PatchFlow in BrainDaemon (Self-Programming Autonomy)

- [x] Wire `PatchFlowOrchestrator.run_cycle()` into BrainDaemon maintenance phase
  - Feature flags:
    - `META_AGENT_PATCHFLOW_RUN=1`
    - `META_AGENT_PATCHFLOW_AUTO_APPLY=0|1` (default 0)
    - `META_AGENT_PATCHFLOW_RUN_TESTS=0|1` (default 0)
  - DoD: offline integration test shows patchflow cycle runs without applying.

- [x] Auto-apply only in sandbox + always run tests before apply
  - DoD: if env is staging/prod, force `auto_apply=False` regardless of env flags.

- [x] Rollback on test failure (sandbox)
  - DoD: apply then fail tests -> rollback executed and audited.

- [x] Bridge SelfProgramming patch store -> PatchFlow queue
  - Files: `meta_agent/patchflow/store_bridge.py`, `meta_agent/patchflow/orchestrator.py`
  - Flag: `META_AGENT_PATCHFLOW_SYNC_STORE=1`
  - DoD: patches written to `data/patches.json` are enqueued into `data/patches/patch_queue.jsonl` for PatchFlow.

- [x] Optional blueprint autopatch maintenance mode (env-gated)
  - File: `quentin/runtime/brain_daemon.py`
  - Flag: `QUENTIN_BRAIN_RUN_BLUEPRINT_AUTOPATCH=1` (sandbox only)
  - DoD: daemon can propose patches (no auto-apply) without manual CLI when enabled.

## P1: Task Sources (Make It Self-Directed)

- [x] Add task sources (v1):
  - blueprint gaps (from `qctl blueprint-scan --emit-evidence`)
  - PatchFlow backlog (needs_review/blocked/rejected/rolled_back)
  - DoD: `python scripts/run_task_sources.py --max-blueprint-tasks 5` enqueues deterministic offline tasks.
  - CLI: `python -m quentin.cli.qctl task-source-run --max-blueprint-tasks 5`

## P2: Real Provider Canary (Safe Enablement)

- [ ] Provide `QUENTIN_CANARY=1` mode:
  - rate-limit calls
  - strict budget caps
  - capture full audit/trace
  - DoD: one canary brain-run is reproducible with logs.
