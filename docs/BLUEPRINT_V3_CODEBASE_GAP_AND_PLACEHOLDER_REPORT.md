# Blueprint v3 vs Codebase: Gaps & Placeholders Report

Date: 2026-02-07

Purpose:
- Capture remaining gaps/placeholders between `blueprint.md` intent and the current codebase reality.
- Convert findings into actionable TODOs (see `docs/TODO_BLUEPRINT_V3_PLACEHOLDER_BACKLOG.md`).

Scope notes:
- `docs/TODO_BLUEPRINT_V3_CHECKLIST.md` is fully checked, but it is not a complete proxy for “no placeholders exist”.
- Automated checks can be misleading:
  - `blueprint/meta_agent_v3_spec.json` is a curated subset (currently 21 requirements), not the full `blueprint.md`.
  - `scripts/analyze_gaps.py` uses mostly import-based probes and can over-report "done".

## A. Spec Coverage Gaps (Audit Coverage Too Small)

1) Evidence audit spec too small
- File: `blueprint/meta_agent_v3_spec.json`
- Finding: 21 requirements are defined (audit coverage is now meaningful), but the spec is still not a complete proxy for `blueprint.md`.
- Impact: `scripts/run_evidence_audit.py` can catch regressions/placeholders for covered requirements, but it cannot claim full blueprint completeness.

2) Probe-based scanner can be overly optimistic
- File: `quentin/blueprint/capability_scanner.py`
- Finding: Static import probes can mark capabilities as "done" even when semantic completeness is missing.
- Impact: `scripts/analyze_gaps.py` reporting "28/28 ok" is not sufficient evidence.

## B. Runtime-Breaking / Tooling-Breaking Placeholders (Highest Priority)

Status (2026-02-07):
- Resolved: blueprint coverage + observability tooling is runnable end-to-end.
- Resolved: `qctl blueprint-scan` can be made fully green deterministically (`--emit-evidence`) without external providers.

Fixes landed:
- `meta_agent/observability/service.py` no longer uses placeholder Patch/Gaps/Research stats; snapshot is built from real local signals.
- `meta_agent/evolution/schedule_state.py` implements stable state persistence (required by coverage tooling).
- `scripts/blueprint_coverage_report.py` runs (integration test exists in repo).

Remaining risks:
- Some optional research runners default to “disabled” (by design) to avoid synthetic metrics unless explicitly enabled.
- Runtime-promoted configs are intentionally gitignored:
  - `config/model_router_rules.json`
  - `config/memory_recall_config.json`

## C. Execution Path Placeholders (System “Can Run” But Not “Do Real Work”)

Status (2026-02-07):
- Major execution-path placeholders are removed or gated behind explicit feature flags.

Fixes landed:
- Meta-Agent research surface is backed by canonical L3 research interface (no in-memory placeholder backend): `meta_agent/research/api.py`.
- PatchFlow is a minimal working pipeline (safety → optional tests → optional apply): `meta_agent/patchflow/orchestrator.py`.
- Legacy/placeholder blueprint loop entrypoint now delegates to canonical blueprint improvement loop: `meta_agent/blueprint/blueprint_loop.py`.

Remaining gaps (non-blocking, by policy):
- Some self-programming helpers may remain feature-flagged/disabled by default to avoid unsafe automation unless explicitly enabled.

## D. “Bridge Logic” That Still Uses Placeholders (Needs Hardening)

1) BlueprintImprover run_once uses guessed file paths
- File: `quentin/blueprint/improver.py`
- Finding: Compatibility bridge constructs placeholder `file_path` guesses from capability IDs.
- Impact: Blueprint->patch automation is not robust; can generate patches for non-existent/incorrect paths.

## E. Research Runners Still Have Stub Defaults (Acceptable Short-Term, But Not Final)

1) Model router offline runner uses stub by default (separate from EvalHarness evaluator)
- File: `quentin/l3/research/runners/model_router_offline_runner.py`
- Finding: default is `_stub_model_router_fn`.
- Impact: If this runner is used, it will not reflect real routing.

2) Patch/skill evolution runners use stub defaults
- Files:
  - `quentin/l3/research/runners/patch_eval_runner.py`
  - `quentin/l3/research/runners/skill_evolution_runner.py`
- Impact: Experiment results can be synthetic unless explicitly provided real eval functions.

## Summary

Remaining gaps are now mostly “policy-driven disabled features” rather than runtime-breaking placeholders:
- Research runners that would otherwise generate synthetic results default to disabled unless explicitly configured.
- A few legacy modules still contain placeholder comments but are not on the canonical execution path.
