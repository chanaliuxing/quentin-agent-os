# Blueprint v3 Placeholder Burn-Down TODOs

Date: 2026-02-07
Source report: `docs/BLUEPRINT_V3_CODEBASE_GAP_AND_PLACEHOLDER_REPORT.md`

Goal:
- Turn “blueprint vs repo” gaps/placeholders into executable, verifiable TODO items.

## P0 (Blockers): Make Coverage & Observability Tooling Runnable

- [x] Fix `SelfEvolutionStateStore` placeholder
- File: `meta_agent/evolution/schedule_state.py`
- Implement: `load()` / `save()` (or equivalent) with a schema-stable JSON file under `data/`
- DoD: `scripts/blueprint_coverage_report.py` runs without crashing

- [x] Replace ObservabilityService blueprint collectors with real data
- File: `meta_agent/observability/service.py`
- Implement: `_collect_blueprint_impl_status/_collect_blueprint_gaps/_collect_blueprint_skills/_collect_blueprint_tests/_collect_blueprint_self_evo`
- DoD: `scripts/blueprint_coverage_report.py` prints a non-empty snapshot-derived summary

- [x] Add regression test: coverage report must run
- File: `tests/integration/test_blueprint_coverage_report_runs.py` (new)
- DoD: `pytest tests/integration -q` includes this test and it passes

## P1: Remove “Execution Path” Placeholders

- [x] Implement real `SkillExecutor.execute`
- File: `meta_agent/skills/executor.py`
- Behavior: load skill from registry/library and execute with structured inputs/outputs
- DoD: `meta_agent/runtime/task_executor.py` can execute at least 1 real skill end-to-end

- [x] Replace `ProgrammerAgent` placeholder with a minimal working implementation (or hard-disable it)
- File: `meta_agent/self_programming/agents/programmer.py`
- DoD: if enabled, it returns at least 1 file modification for a simple change; if disabled, routing never selects it

- [x] Replace `ResearchTool` placeholder (or move behind an explicit feature flag)
- File: `meta_agent/tools/research/research_tool.py`
- DoD: self-programming context building uses real retrieval/summarization when enabled; otherwise clearly degrades without lying

- [x] Implement non-placeholder `BlueprintObjectiveEvaluator`
- File: `meta_agent/blueprint/objective_evaluator.py`
- DoD: blueprint loop produces structured objective-eval output with pass/fail + reasons

- [x] Fix invalid `JsonlTraceRecorder("logs/...")` usage across `meta_agent/*`
- Files: multiple (search `JsonlTraceRecorder("logs/`)`
- Implement: use `JsonlTraceRecorder(repo_root=".")` and ensure every `record_event(...)` includes `trace_id`
- DoD: `rg 'JsonlTraceRecorder\\(\"logs/' meta_agent` returns empty; trace events append under `data/traces/` when invoked

- [x] Remove `CodeToolBackend` placeholder bridge referenced by YAML paths
- File: `meta_agent/evolution/code_tool_backend_stub.py`
- Implement: re-export canonical `meta_agent.tools.code_tools.CodeToolBackend`
- DoD: YAML import paths resolve without stubs

## P2: Harden Blueprint->Patch Automation (Remove Placeholder Bridges)

- [x] Remove guessed placeholder file-path logic in `BlueprintImprover.run_once`
- File: `quentin/blueprint/improver.py`
- Implement: use real module hints from a machine spec or run a resolver that finds the correct target file
- DoD: “gap -> patch proposal” never targets non-existent files in a clean repo

## P3: Expand Machine-Readable Blueprint Spec Coverage

- [x] Expand `blueprint/meta_agent_v3_spec.json` to cover v3 blueprint critical path
- Include at least:
- Lanes/Abort/Session lock
- SafetyKernel guard for llm/tool/code_patch/deploy
- Memory: promotion/decay batch + hybrid recall
- Research: decide_and_promote_variant + online apply (sandbox/staging)
- DoD: `scripts/run_evidence_audit.py` reports on >= 20 requirements and flags placeholders as penalties

## P4: Reduce Stub Defaults In Research Runners

- [x] Make model_router runner use canonical `quentin.routing.model_router.ModelRouter` by default
- File: `quentin/l3/research/runners/model_router_offline_runner.py`
- DoD: runner output reflects variant params routed through ModelRouter (no `_stub_model_router_fn`)

- [x] Replace patch_eval/skill_evolution stub fns with minimal real implementations or explicit “disabled” errors
- Files:
- `quentin/l3/research/runners/patch_eval_runner.py`
- `quentin/l3/research/runners/skill_evolution_runner.py`
- DoD: experiments do not silently generate synthetic results unless explicitly requested
