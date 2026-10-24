# TODO: Modular Task Sources (Registry + Priorities)

Date: 2026-02-11
Scope: `quentin/runtime/task_sources.py`, `quentin/runtime/brain_daemon.py`, `tests/*`

Problem:
- Task sources are currently wired via scattered env toggles and direct calls.
- When a source fails or returns 0 items, the runtime cannot "sense" why and tends to re-enter a planning loop.
- Adding a new task source requires editing core code (not pluggable).

Goal:
- Introduce a `TaskSource` interface and a registry to register sources by ID.
- Support priorities, enable/disable flags, and run budgets.
- Emit structured run reports so the brain can sense: "no-op vs error vs disabled vs throttled".

Non-goals:
- Do not change task queue storage format.
- Do not change the existence of blueprint/patchflow/observability sources; only re-wire them.

Design (proposal):
- New protocol:
  - `TaskSourceSpec(id, name, kind, priority, default_enabled, max_per_run, cooldown_sec)`
  - `TaskSource.run(ctx) -> TaskSourceRunReport`
- Registry:
  - `TaskSourceRegistry.register(source: TaskSource)`
  - `TaskSourceRegistry.list_specs()`
  - `TaskSourceRegistry.run_enabled(ctx) -> CombinedReport`
- Enable rules:
  - `QUENTIN_TASK_SOURCES_REGISTRY=1` enables registry mode.
  - Keep legacy env flags (e.g. `QUENTIN_TASK_SOURCE_BLUEPRINT`) but interpret them inside the registry (back-compat).
- Sensing:
  - Standard `details[].reason` values: `disabled`, `cooldown`, `budget_exhausted`, `no_candidates`, `error`.
  - Standard counters: `enqueued`, `skipped`, `errors`, `duration_ms`.

Implementation Steps:
- [x] Add `quentin/runtime/task_source_registry.py` with `TaskSource`, `TaskSourceRegistry`, `TaskSourceContext`.
- [x] Refactor `quentin/runtime/task_sources.py`:
  - [x] Convert `enqueue_blueprint_gap_tasks`, `enqueue_patchflow_backlog_tasks`, `enqueue_anomaly_tasks` into `TaskSource` implementations.
  - [x] Move implementations to modular files in `quentin/runtime/task_sources/`.
  - [x] Update `run_task_sources_once()` to use registry when enabled.
- [x] Update `quentin/runtime/brain_daemon.py`:
  - [x] When a task source run yields 0 tasks, record the combined report into trace/system-events.
  - [x] Add a `self_awareness_note` string summarizing reasons (so the executor stops "re-planning blindly").
- [x] Add trace + events:
  - [x] Extend `quentin/runtime/system_events.py` to include `task_source_run_report` event type (text-only payload).
- [x] Tests:
  - [x] `tests/unit/test_task_source_registry.py` (register/list/priorities, enable logic, cooldown).
  - [x] `tests/integration/test_task_sources_registry_run.py` (runs in a temp repo, asserts reports).

Acceptance Criteria:
- Can add a new task source without editing `task_sources.py` (register via registry bootstrap).
- Brain can distinguish:
  - disabled vs no_candidates vs error.
- No regression: legacy env toggles still work.

Rollback:
- Set `QUENTIN_TASK_SOURCES_REGISTRY=0` to use legacy behavior.
