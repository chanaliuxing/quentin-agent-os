# OpenClaw Planning Gap Assessment & Landing TODO (Quentin)

Updated: 2026-02-21

## Status Snapshot
- P0: implemented
- P1: implemented
- P2: implemented (with benchmark harness + trend report script)
  - benchmark script: `scripts/planning_process_benchmark.py`
- P3-1: implemented (verify threshold auto-calibration from benchmark history)
  - includes domain-bucket calibration with global fallback

## 1) Current Gap Size (Quantified)

Scope baseline (OpenClaw parity target):
- `payloads.ts` (~1200)
- `attempt.ts` (~600)
- `params.ts` (~200)
- `images.ts` (~300)

Estimated parity status in Quentin (engineering assessment):

| Area | Target Capability | Current | Residual Gap |
|---|---|---:|---:|
| Payload pipeline (`payloads.ts`) | Stage-aware + retry-aware + tool-aware prompt factory | ~84% | ~16% |
| Attempt runtime (`attempt.ts`) | extraction/guard/interruption/reset survival logic | ~82% | ~18% |
| Param hedge (`params.ts`) | token-pressure adaptive model params | ~76% | ~24% |
| Vision budget (`images.ts`) | multi-modal budget routing/quality strategy | ~72% | ~28% |
| **Overall weighted planning layer** | end-to-end planning intelligence | **~82%** | **~18%** |

Notes:
- This is feature-parity scoring, not LOC parity scoring.
- Main remaining gaps moved from core behavior to calibration/coverage depth.

## 2) What Is Already Landed

- Lifecycle payload matrix (`initial/retry/stuck`) with speculative-on-stuck.
- Failure-category strategy patch + retry delta injection.
- Tool family + tool subcategory payload variants.
- Tool-only loop force-progress-sync injection (>=3 no-update tool turns).
- Weighted retry budget by failure severity/origin.
- Deterministic input preprocessing (command/directive/inline-action) with allowlist.
- `<think>/<final>` parsing + repetition detection.
- Planner reset after repeated failures (`QUENTIN_PLANNER_RESET_FAILURE_THRESHOLD`).
- XML truncation incremental repair (`<think>/<final>/<answer>` close-up).
- Verify gate now checks process intelligence (`strategy_switch_effectiveness`).
- Auto loop recovers from strategy-switch failures with subtype-focused recovery prompts.

## 3) Remaining High-Value Gaps

### G1. Benchmark corpus breadth
- Status:
  - implemented: long-tail replay expanded to 20 archetypes with regression sensitivity assertions.

### G2. Calibration recommendations CI governance
- Status:
  - implemented: CI workflow now generates recommendation + env patch artifacts and enforces drift gate with approval file override.

### G3. Vision feedback judge signals
- Status:
  - implemented: effective outcome score now blends heuristic score with judge/confidence signals for feedback adaptation.

## 4) Landing TODO (Prioritized)

## P3 (current)

1. Verify threshold auto-calibration
- Files:
  - `verify_system.py`
  - `scripts/planning_process_benchmark.py`
- Deliver:
  - derive recommended thresholds from rolling benchmark history percentile.
- Acceptance:
  - threshold recommendation report generated with rollback-safe defaults.
 - Status: done

2. Benchmark corpus expansion (real-world traces)
- Files:
  - `tests/integration/`
  - `generated/benchmarks/` (runtime artifacts only)
- Deliver:
  - add at least 10 new planning-failure archetypes and replay harness.
- Acceptance:
  - benchmark score variance is stable and sensitive to injected regressions.
 - Status: implemented (20-archetype long-tail replay + injected degradation detection in `tests/integration/test_planning_process_benchmark_longtail.py`)

5. Threshold recommendation automation
- Files:
  - `scripts/planning_threshold_recommendation.py`
  - `scripts/planning_threshold_env_patch.py`
  - `generated/benchmarks/planning_threshold_recommendation.json`
  - `generated/benchmarks/planning_threshold_env_patch.env`
- Deliver:
  - generate per-bucket threshold recommendations with global fallback.
- Acceptance:
  - recommendation artifact generated in CI and reviewed before threshold updates.
 - Status: implemented (recommendation + env patch artifact + autoloop wiring + CI drift gate)

3. Adaptive interrupt cooldown tuning
- Files:
  - `quentin/cognitive/loop_orchestration.py`
  - `quentin/diagnostics/intelligence_auditor.py`
- Deliver:
  - cooldown length policy tied to repeated subtype/failure origin.
- Acceptance:
  - lower loop recurrence without harming completion rate.
 - Status: implemented (adaptive cooldown + recurrence telemetry)

4. Vision feedback-closed policy
- Files:
  - `quentin/cognitive/vision_budget.py`
  - `quentin/observability/service.py`
- Deliver:
  - collect outcome signal and adjust future budget profile by task class.
- Acceptance:
  - measurable quality lift on multimodal benchmark subset.
 - Status: implemented (feedback record/apply + judge-signal blending + observability summary)

## 5) Suggested Execution Order (2-week practical plan)

1. Week 1:
- Finish P0-1 and P0-2 first (interrupt + integrity).
- Then wire P0-3 verify gate metrics.

2. Week 2:
- Implement P1 attempt-indexed escalation.
- Then provider-aware param hedge and adaptive vision budget.
- End with P2 authz hardening + benchmark harness.

## 6) Done Definition

This planning parity track can be considered "engineering complete" when all conditions hold:
- `verify_system.py` process gate blocks low-quality planning behavior reliably.
- Repetition/tool-loop tasks converge by interrupt/reset policy without manual rescue.
- XML/JSON truncation no longer breaks chain continuity in benchmark corpus.
- Payload strategy escalates deterministically with retry stage and attempt band.
- Provider/tool changes are env-only (no planner code edits required).
