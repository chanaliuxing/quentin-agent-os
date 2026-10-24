# TODO: Quentin Runtime Intelligence Upgrade

Date: 2026-02-10

## P0 - Must Land
- [x] Planner: add discovery-before-risky-operation hard instruction.
- [x] Planner: inject forbidden actions from recent audit denials/errors.
- [x] Planner: replace `planner_fallback_single_step` with 3-step decomposed fallback.
- [x] Planner: add quality repair pass:
  - [x] inject discovery precheck when risky steps lack prior discovery
  - [x] prevent single-step regression by reusing previous decomposition
- [x] Executor: inject forbidden-action feedback into execution prompt.
- [x] DoneCouncil: add weak-reasoning guard for non-done verdicts.
- [x] DoneCouncil: add strict retry path with evidence requirement.
- [x] DoneCouncil: deterministic fallback reason from execution evidence.
- [x] GoalDoneManager: consume council confidence when present.

## P1 - Test & Verification
- [x] Add unit tests for planner hint forbidden actions.
- [x] Add unit tests for plan quality repair behaviors.
- [x] Add unit tests for executor forbidden-action prompt injection.
- [x] Add unit tests for DoneCouncil quality-retry/fallback paths.
- [x] Run focused test matrix:
  - [x] `tests/unit/test_cognitive_loop_metrics.py`
  - [x] `tests/unit/test_executor_prompt_style.py`
  - [x] `tests/unit/test_done_council_quality.py`
  - [x] `tests/unit/test_cognitive_loop_prompt_factory.py`
  - [x] `tests/unit/test_goal_manager.py`

## P2 - Observability Follow-up
- [x] Add dashboard counters:
  - [x] planner repair reason counts
  - [x] blocked action recurrence (e.g., nano/wget repeats)
  - [x] done-council weak-reasoning retry rate
- [x] Add intelligence summary + warning alerts into dashboard snapshot.
- [x] Add trace-level audit for "discovery step present before risky action".

## P3 - Optional Hardening
- [x] Feature flag for strict council-quality enforcement:
  - [x] env: `QUENTIN_DONE_COUNCIL_STRICT_REASONING=1`
  - [x] runbook for rollback if false positives appear
- [x] Brain daemon autoregression hardening:
  - [x] read observability intelligence metrics on interval
  - [x] auto-enable strict mode when repair/recurrence/compliance signals degrade
  - [x] auto-restore baseline strictness env when strict window expires
  - [x] persist strict-window state in `data/runtime/brain_guardrail_state.json`

## P4 - Metacognitive Audit Integration
- [x] Add deterministic `intelligence_auditor` for four symptom families:
  - [x] guessing trap
  - [x] semantic stagnation
  - [x] strategy regression
  - [x] self-awareness gap
- [x] Add CLI script `scripts/audit_intelligence_regressions.py`.
- [x] Integrate audit summary into dashboard snapshot + warning alerts.
- [x] Extend static overview dashboard rendering with audit cards.

## P5 - Runtime Self-Healing Loop
- [x] Add automatic recovery task injection when intelligence strict mode is triggered.
- [x] Ensure recovery tasks are deduplicated by regression reason set.
- [x] Record intelligence recovery outcomes and persist rolling success-rate state.

## P6 - Unified Observability Output
- [x] Expose `intelligence_audit` in `ObservabilityService.get_overview()` output.
- [x] Keep dashboard renderer compatible with overview-native `intelligence_audit`.
- [x] Expose intelligence recovery-loop metrics (`success_rate`, `sample_size`) in observability intelligence domain.
- [x] Add dashboard warning for low intelligence recovery success rate.
- [x] Add recovery trend metrics (`recent_window_rate`, `prior_window_rate`, `trend_delta`) in observability output.
- [x] Add dashboard warning for recovery trend deterioration (`intelligence_recovery_trend_down`).

## P7 - Reason-Specific Recovery Templates
- [x] Generate intelligence recovery task content from reason-based templates (guessing/semantic/strategy/self-awareness).
- [x] Persist recovery focus label in task metadata (`recovery_focus`).
- [x] Aggregate recovery focus breakdown in observability metrics (total/done/failed/success_rate).
- [x] Add dashboard warning for low-performing recovery focus (`intelligence_recovery_focus_low`).
