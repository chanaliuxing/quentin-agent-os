# Blueprint v3: Next Steps TODO (Post "All Green")

Date: 2026-02-07
Related:
- Plan: `docs/BLUEPRINT_V3_NEXT_IMPLEMENTATION_PLAN.md`
- Blueprint: `blueprint.md`
- Gap reports:
  - `docs/BLUEPRINT_V3_REMAINING_GAPS_AND_NEXT_ACTIONS.md`
  - `docs/BLUEPRINT_V3_CODEBASE_GAP_AND_PLACEHOLDER_REPORT.md`

Goal:
- Turn remaining "research-grade" gaps into executable, verifiable TODOs.

---

## P0: Close ImmuneLoop Feedback Loop (L3->L2->L1)

- [x] Add EvalHarness evaluator for `immune_loop`
  - [x] File: `quentin/l3/research/eval_harness.py`
  - [x] Behavior: deterministic synthetic traces -> run ImmuneLoop -> return `EvalCaseResult`
  - [x] DoD: `pytest tests/integration -q` includes an immune evaluator test and passes.

- [x] Add runtime defaults loader for ImmuneLoop thresholds (feature-flagged)
  - [x] Files:
    - `quentin/loops/immune_loop.py`
    - `quentin/loops/immune_defaults.py` (new)
  - [x] Env:
    - `QUENTIN_IMMUNE_DEFAULTS_ENABLE=1`
    - `QUENTIN_IMMUNE_DEFAULTS_PATH` (optional; default `config/immune_loop_config.json`)
  - [x] DoD: defaults do not affect behavior unless enable flag is set.

- [x] Extend promotion apply to support ImmuneLoop
  - [x] File: `quentin/l3/research/experiment_orchestrator.py`
  - [x] Behavior: when `target_module == "immune_loop"` write promoted params to config json.
  - [x] DoD: promotion works in sandbox/staging; refuses in prod.

- [x] Add script: immune loop offline A/B -> promote -> runtime effect
  - [x] File: `scripts/run_immune_loop_feedback_loop.py` (new)
  - [x] DoD: `python scripts/run_immune_loop_feedback_loop.py` exit 0, prints decision + applied=true.

- [x] Add integration test for immune feedback loop
  - [x] File: `tests/integration/test_immune_feedback_loop_runs.py` (new)
  - [x] DoD: test does not depend on external LLM/providers and runs under `pytest -q`.

- [x] Ignore promoted immune defaults
  - [x] File: `.gitignore`
  - [x] Add: `/config/immune_loop_config.json`

## P0: Research Runner Stub Policy (No Synthetic Metrics By Default)

- [x] Enforce "disabled by default" for any runner that would otherwise generate synthetic metrics
  - [x] Files:
    - `quentin/l3/research/runners/patch_eval_runner.py`
    - `quentin/l3/research/runners/skill_evolution_runner.py`
  - [x] DoD: without `ALLOW_STUB_RESEARCH_RUNNERS=1` or explicit fn injection, runner raises a clear `RuntimeError`.

- [x] Add regression test: stub runners must be explicit
  - [x] File: `tests/unit/test_research_runners_stub_policy.py` (new)
  - [x] DoD: unit test asserts default behavior is disabled and message mentions `ALLOW_STUB_RESEARCH_RUNNERS`.

## P1: Blueprint Coverage Expansion (Beyond Curated Radar Spec)

- [x] Add a section-oriented machine spec (blueprint.md narrative)
  - [x] File: `blueprint/spec_v3_sections.json` (new)
  - [x] DoD: spec includes >= 40 items; items reference real modules and strict trace_signals.

- [x] Add regression: spec must not shrink
  - [x] File: `tests/integration/test_blueprint_specs_min_coverage.py` (new)
  - [x] DoD: fails if `spec_v3_sections.json` drops below min count.

## P1: Minimal HTML Dashboard (Offline)

- [x] Render static HTML from `ObservabilityService.get_overview()`
  - [x] File: `scripts/render_overview_dashboard.py` (new)
  - [x] Output: `data/observability/overview.html` (ignored)
  - [x] DoD: `python scripts/render_overview_dashboard.py` exit 0; file exists and includes key metrics keys.

- [x] Add smoke test: dashboard render script runs
  - [x] File: `tests/integration/test_render_overview_dashboard_runs.py` (new)
  - [x] DoD: runs under `pytest -q`, no network required.
