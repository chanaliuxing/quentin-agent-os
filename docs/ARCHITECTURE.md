# Architecture (Canonical Paths & Duplicates)

Date: 2026-02-06

This repo contains multiple overlapping implementations of similar concepts (loops, orchestrators, tool managers).
To keep the runtime predictable, this document names the intended **canonical** modules and records known duplicates.

## Canonical Modules (v3 Target)

- Cognitive Loop (entrypoint): `quentin/cognitive/loop.py` (implementation: `quentin/cognitive/loop_impl.py`)
- Sleep Loop (entrypoint): `quentin/sleep/loop.py` (implementation: `quentin/sleep/loop_impl.py`)
- Immune Loop: `quentin/immune/loop.py`
- Experiment Orchestrator: `quentin/l3/research/experiment_orchestrator.py`
- Eval Harness: `quentin/l3/research/eval_harness.py`
- Model Router (unified): `quentin/routing/model_router.py`
- Tool Manager (governance + hooks): `quentin/tools/manager.py`
- Safety Kernel: `quentin/kernel/safety.py` + `quentin/kernel/policy.py` + `quentin/kernel/budget.py`
- Persistent KVStore: `quentin/infra/storage/kv_store.py`
- Self-Programming Engine: `meta_agent/self_programming/engine_v2.py` (preferred) with `quentin/self_programming/legacy_selfprog/` as legacy code location

## Known Duplicates (Needs Migration/Deprecation)

> Legend:
> - **Used by** is based on repo-local call sites as of 2026-02-06.
> - **Status**: `canonical` / `wrapper` / `legacy` / `placeholder`.

### CognitiveLoop

| Path | Used by | Status | Notes |
|---|---|---|---|
| `quentin/cognitive/loop.py` | `quentin/bootstrap/container.py` | canonical | Stable import path for orchestration code. |
| `quentin/cognitive/loop_impl.py` | `quentin/cognitive/loop.py` | canonical | Actual implementation (planner/executor/immune/reflection). |
| `quentin/runtime/cognitive_loop.py` | `quentin/runtime/system.py:build_default_runtime` | wrapper | Delegates to canonical core loop but preserves `TaskResult` contract + trace recorder. |
| `quentin/core/*` | legacy call sites | removed | The `quentin/core` directory has been removed; callers must import canonical modules under `quentin/cognitive`, `quentin/execution`, `quentin/traces`, `quentin/routing`, etc. |
| `meta_agent/evolution/cognitive_loop.py` | unknown | legacy | Consider delegating to `quentin/cognitive/loop_impl.py`. |

### SleepLoop

| Path | Used by | Status | Notes |
|---|---|---|---|
| `quentin/sleep/loop.py` | `quentin/bootstrap/container.py` | canonical | Stable import path for orchestration code. |
| `quentin/sleep/loop_impl.py` | `quentin/sleep/loop.py` | canonical | Actual implementation (consolidation + training pairs + skill candidates). |
| `quentin/runtime/sleep_loop.py` | `quentin/runtime/system.py:build_default_runtime` | wrapper | Runtime bootstrap wiring; should delegate to canonical over time. |
| `quentin/memory/sleep_loop.py` | legacy call sites | wrapper | Backward-compat re-export of the canonical implementation. |
| `quentin/loops/sleep_loop.py` | legacy call sites | wrapper | Sync facade over canonical async SleepLoop. |
| `meta_agent/evolution/sleep_loop.py` | unknown | legacy | Consider delegating to `quentin/memory/sleep_loop.py`. |

### ImmuneLoop

| Path | Used by | Status | Notes |
|---|---|---|---|
| `quentin/immune/loop.py` | `quentin/cognitive/loop_impl.py` + `quentin/bootstrap/container.py` | canonical | Handles after-attempt + immune cases. |
| `quentin/runtime/immune_loop.py` | `quentin/runtime/system.py:build_default_runtime` | wrapper | Runtime bootstrap wiring. |
| `quentin/core/immune_loop.py` | unknown | removed | Legacy `ImmuneLoop` implementation removed; use `quentin/loops/immune_loop.py` or `quentin/immune/loop.py` depending on loop surface. |
| `quentin/loops/immune_loop.py` | `quentin/cli/qctl.py` imports (legacy commands) | legacy | CLI still imports it for old commands; should migrate. |
| `meta_agent/evolution/blueprint_loop.py` | unknown | legacy | Not the same responsibility; keep separate or rename. |

### ExperimentOrchestrator

| Path | Used by | Status | Notes |
|---|---|---|---|
| `quentin/l3/research/experiment_orchestrator.py` | `quentin/bootstrap/container.py` | canonical | Guarded/audited experiment execution. |
| `quentin/l3/research/experiments.py` | CLI + misc research code | facade | File-backed experiment store; not yet fully aligned with orchestrator v1. |
| `quentin/l3/research/orchestrator.py` | unknown | legacy | Candidate for deprecation. |
| `quentin/experiments/orchestrator.py` | unknown | legacy | Candidate for deprecation. |

### EvalHarness

| Path | Used by | Status | Notes |
|---|---|---|---|
| `quentin/l3/research/eval_harness.py` | `quentin/l3/research/experiment_orchestrator.py` | canonical | Supports evaluator registry; includes `target_type=planner` evaluator. |
| `quentin/eval/harness.py` | eval tooling | legacy | Older/simple harness used by some experiments tooling; candidate for deprecation once unified. |
| `quentin/evaluation/harness.py` | unknown | legacy | Candidate for deprecation. |

### ToolManager

| Path | Used by | Status | Notes |
|---|---|---|---|
| `quentin/tools/manager.py` | `quentin/bootstrap/container.py` + `quentin/execution/executor.py` | canonical | Policy stacking + non-bypass SafetyKernel guard + trace/audit + cancellation. |
| `meta_agent/tools/*` | Self-programming engine | separate | Not yet unified; can be bridged later. |

### SelfImprovementManager

- `quentin/self_improvement/manager.py`
- `quentin/meta/self_improvement.py`

### SelfProgrammingEngine

- `meta_agent/self_programming/engine_v2.py` (canonical target in v3 wiring)
- `quentin/self_programming/legacy_selfprog/engine.py` (legacy location)
- `quentin/self_programming/engine.py` (legacy / alternate implementation)

## Migration Notes

- Prefer updating callers to import canonical modules directly (avoid re-export chains).
- Add explicit deprecation warnings for legacy modules once runtime call sites are confirmed migrated.
- Keep compatibility shims small and logged (warnings should point to the canonical module).
