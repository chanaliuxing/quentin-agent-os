# Blueprint v3: Next Implementation Plan (Post "All Green")

Date: 2026-02-07

Purpose:
- The repo can now run offline end-to-end (scan/evidence/feedback loops/bench).
- This plan focuses on closing the remaining gaps where "tools can run" is not yet "runtime-grade + research-grade".

Guiding principles:
- Prefer feature-flagged hardening; default paths remain runnable offline.
- Avoid synthetic metrics by default; stubs must be explicit and traceable.
- Every new loop/promotion path must ship with: (1) integration test, (2) micro-benchmark or regression metric.

## Milestone A (P0): Make L3->L2->L1 Feedback Loops Cover ImmuneLoop

Goal:
- Add a third closed feedback loop: ImmuneLoop thresholds -> offline evaluation -> promotion -> runtime defaults.

Deliverables:
- EvalHarness evaluator: target_type `immune_loop` (deterministic, offline).
- Promotion apply: `config/immune_loop_config.json` (gitignored) + explicit enable flag.
- Script: `scripts/run_immune_loop_feedback_loop.py` (exit 0, self-checks).
- Integration test: feedback loop runs and applies defaults.

## Milestone B (P0): Remove "Implicit Stub" Risk in Research Runners

Goal:
- Ensure no experiment runner returns synthetic metrics unless explicitly enabled.

Deliverables:
- Runners default to `disabled` with a clear error (or require explicit fn injection).
- Integration tests assert disabled-by-default behavior.
- Docs: list env flags (`ALLOW_STUB_RESEARCH_RUNNERS`, etc).

## Milestone C (P1): Expand Blueprint Coverage Beyond Curated Radar Spec

Goal:
- Increase confidence that "green" correlates with the narrative blueprint.

Deliverables:
- Add a second machine spec focused on blueprint.md sections (not just engineering primitives).
- Add a doc mapping: blueprint.md -> spec items -> evidence (trace/exp/file).
- Add regression: spec must not shrink (min item count) and key items must have strict trace_signals.

## Milestone D (P1): Observability UX (Minimal, Useful Dashboard)

Goal:
- Move beyond JSON overview to a view that humans can use in research/debug.

Deliverables:
- A script that renders a static HTML dashboard from `ObservabilityService.get_overview()`.
- A smoke test that the script runs offline and produces the HTML artifact under `data/` (ignored).

## Milestone E (P1): Real External LLM Execution (Opt-in)

Goal:
- Run CognitiveLoop end-to-end with a real external provider (OpenAI/Gemini/DeepSeek) without changing default offline behavior.

Deliverables:
- Provider clients wired through `quentin/llm/client.py:call_llm` with `LLM_PROVIDER` + provider-specific env vars.
- Smoke script: `scripts/run_real_llm_smoke.py`.
- Unit tests: provider call surfaces are verified with httpx mocking (no network).
- Env-gated integration smoke: `REAL_LLM_SMOKE=1` enables a real-network call in `tests/integration/`.
- Docs runbook: `docs/REAL_LLM_EXECUTION_PLAN.md`.
