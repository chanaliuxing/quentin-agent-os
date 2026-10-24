# Blueprint v3 Next Phase TODO (Post-checklist)

Date: 2026-02-08
Purpose:
- `docs/TODO_BLUEPRINT_V3_CHECKLIST.md` is mostly “P0/P1 main path” closure and canonicalization.
- This file tracks the next batch of work needed for “the brain runs itself” and “L3→L2→L1 feedback loop” beyond the original checklist.

References:
- Blueprint: `blueprint.md`
- Gap/placeholder reports:
  - `docs/BLUEPRINT_V3_REMAINING_GAPS_AND_NEXT_ACTIONS.md`
  - `docs/BLUEPRINT_V3_CODEBASE_GAP_AND_PLACEHOLDER_REPORT.md`
- Autonomy TODO: `docs/TODO_AUTONOMY_BRAIN.md`

---

## A. L3→L2→L1 “Always-on” closure (system, not scripts)

- [ ] Add an always-on “evolution cycle” runner
  - File: `scripts/run_evolution_feedback_loop.py` (currently script-level), promote to daemon mode
  - DoD: can run `--max-cycles N` with deterministic offline defaults and produces structured reports.

- [ ] Convert blueprint gaps → patch proposals → PatchFlow queue (end-to-end)
  - Files: `quentin/blueprint/auto_patcher.py`, `meta_agent/patchflow/orchestrator.py`
  - DoD: with `--run-selfprog` and a real coder backend, at least 1 real patch is enqueued into PatchFlow queue.

- [ ] Release protocol: shadow/canary metrics gate (sandbox first)
  - Files: `quentin/l3/research/release_protocol.py`, `meta_agent/self_programming/engine_v2.py`
  - DoD: “promotion” requires a minimal metric delta + budget gate + SafetyKernel decision log.

---

## B. Task Sources (self-directed maintenance)

- [x] Task sources v1: blueprint gaps + PatchFlow backlog
  - Files: `quentin/runtime/task_sources.py`, `scripts/run_task_sources.py`
  - DoD: tasks are enqueued deterministically without external providers.

- [ ] Task sources v2: observability anomalies → remediation tasks
  - File: `quentin/observability/service.py` (+ new detector)
  - DoD: when error/latency/tokens exceed thresholds, a remediation task is queued with evidence payload.

---

## C. Benchmarks (so the brain can verify improvements)

- [x] Memory recall benchmark
  - File: `scripts/bench_memory_recall.py`

- [x] TaskQueue throughput benchmark
  - File: `scripts/bench_task_queue_offline.py`

- [ ] End-to-end autonomy benchmark (queue → loops → patchflow)
  - File: `scripts/bench_autonomy_end_to_end.py` (new)
  - DoD: reports tasks/sec + patchflow cycle latency; env-gated for real providers.

---

## D. Repo hygiene / reproducibility

- [x] Fix OpenClaw submodule mapping
  - File: `.gitmodules`
  - DoD: `git submodule status` works on a fresh clone.

