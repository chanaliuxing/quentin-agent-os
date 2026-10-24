# Blueprint v3: Modular + Pluggable Upgrade Plan (No Architecture Changes)

Date: 2026-02-11

Goal:
- Make Quentin easier to evolve by making "hands/feet" and "sensing" capabilities pluggable.
- Keep the current Blueprint architecture and main responsibility boundaries intact.
- Default safe: every new capability is feature-flagged and can be rolled back cleanly.

Non-goals:
- No new top-level runtime layer.
- No big refactors that move existing responsibilities between Runtime/CognitiveLoop/ToolManager/SelfProgramming.
- No GUI/visualization work in this plan (text-only sensing).

Principles (must follow):
- Registry over conditionals: prefer explicit registries to scattered `if env:` blocks.
- Pluggable by construction: each "block" has an interface + default implementation.
- Evidence-first: every block defines trace signals and has unit/integration tests.
- Back-compat: keep existing env knobs working until the new registry is stable.

What is already landed (baseline; do not redo here):
- Tool plugin platform + cache policy (manifest-driven, SWR, key_fields).
- Skill markdown metadata + lazy SOP loading.
- Self-programming isolated workdir (opt-in).
- Controlled interactive shell tool (opt-in).
- Background system events unification + API endpoint.
- Prompt migration feature flags + trace prefix unification.
- Progressive pressure + self-awareness hooks in executor (done in prior TODOs).
- Model dialect adaptation helper (provider/model-aware prompt compaction).

---

## Phase P1 (High ROI, Low Invasiveness): Normalize Plug Points

P1 focus:
- Make the "where do tasks/tools/skills come from" explicit and pluggable.
- Reduce "try-loop" failures by providing structured sensing and deterministic fallback paths.

Blocks:
- P1-A TaskSource registry (replace hardcoded env toggles)
  - TODO: `docs/improve/TODO_MODULAR_TASK_SOURCES_2026-02-11.md`
- P1-B ToolPack registry (move builtin tool registration into packs)
  - TODO: `docs/improve/TODO_MODULAR_TOOL_PACKS_2026-02-11.md`
- P1-C Tool middleware pipeline (before/after hooks as a chain)
  - TODO: `docs/improve/TODO_TOOL_MIDDLEWARE_PIPELINE_2026-02-11.md`
- P1-D Tool-call protocol adapters (native tools vs JSON fallback)
  - TODO: `docs/improve/TODO_TOOL_CALL_PROTOCOLS_2026-02-11.md`
- P1-E Context snapshot providers (file-tree / env probes for "no hallucination")
  - TODO: `docs/improve/TODO_CONTEXT_SNAPSHOT_PROVIDERS_2026-02-11.md`

Acceptance for P1:
- There is a single, testable registration surface per block.
- Default behavior remains unchanged when flags are off.
- Executor can "sense" blocked actions and switch to a non-interactive path without re-planning loops.

---

## Phase P2 (Medium ROI, Medium Invasiveness): Swap Backends Cleanly

P2 focus:
- Make "where data lives and how it is persisted" swappable.
- Provide isolated runtimes for plugins and avoid cross-plugin contamination.

Blocks:
- P2-A Skill backends (filesystem/registry/exec-skill) behind a single interface
  - TODO: `docs/improve/TODO_SKILL_BACKENDS_2026-02-11.md`
- P2-B Self-programming backends (runner/applier/patch store/git adapter)
  - TODO: `docs/improve/TODO_SELF_PROGRAMMING_BACKENDS_2026-02-11.md`
- P2-C Observability sinks + event store backends (file/sqlite/no-op)
  - TODO: `docs/improve/TODO_OBSERVABILITY_SINKS_AND_EVENT_STORE_2026-02-11.md`
- P2-D Plugin runtime isolation (namespace + capability gating)
  - TODO: `docs/improve/TODO_PLUGIN_RUNTIME_ISOLATION_2026-02-11.md`

Acceptance for P2:
- Each backend has a stable interface with a default implementation.
- Switching backend is config-only (env or Settings), no code changes.
- Backends emit consistent trace signals and errors are actionable.

---

## Phase P3 (Optional, Higher Leverage): Governance + Safety as Modules

P3 focus:
- Make Safety/Policy governance composable: add new interceptors without editing core.
- Extend evaluation/bench to be plugin-friendly.

Blocks:
- P3-A Policy + security interceptors registry (hard gates in kernel)
  - TODO: `docs/improve/TODO_POLICY_AND_SECURITY_INTERCEPTORS_2026-02-11.md`
- P3-B Eval/bench plugins (new evaluators without touching core harness)
  - TODO: `docs/improve/TODO_EVAL_AND_BENCH_PLUGINS_2026-02-11.md`
- P3-C Router policies as plugins (provider/model routing strategies)
  - TODO: `docs/improve/TODO_ROUTER_AND_DIALECT_PLUGINS_2026-02-11.md`

Acceptance for P3:
- Kernel enforces safety regardless of prompt quality.
- Adding a new evaluator/router strategy is a new module + manifest, not editing core files.

---

## Unified Rollout Controls (Flags)

Recommended policy:
- Every block has a `QUENTIN_*_ENABLED` flag defaulting to safe/off unless it is a pure refactor with no behavior changes.
- Every block has a one-command smoke check in `scripts/` (offline).
- Every block has a rollback knob: revert to legacy path by env var.

Suggested names (to be used in TODOs):
- `QUENTIN_TASK_SOURCES_REGISTRY`
- `QUENTIN_TOOL_PACKS_ENABLED`
- `QUENTIN_TOOL_MIDDLEWARE_PIPELINE`
- `QUENTIN_TOOL_CALL_PROTOCOLS`
- `QUENTIN_CONTEXT_SNAPSHOT_PROVIDERS`
- `QUENTIN_SKILL_BACKEND`
- `QUENTIN_SELFPROG_BACKEND`
- `QUENTIN_OBS_EVENT_STORE_BACKEND`
- `QUENTIN_PLUGIN_RUNTIME_ISOLATION`
- `QUENTIN_POLICY_INTERCEPTORS`
- `QUENTIN_EVAL_PLUGINS_ENABLED`

---

## Status Tracking

This plan is an index. Each block is executed via its own TODO doc (with DoD, tests, and rollback).

