# Done Council Strict Reasoning Runbook

Date: 2026-02-10
Scope: `quentin/council/done.py`, `quentin/runtime/brain_daemon.py`

## Purpose
Keep done-verdict quality high by requiring evidence-backed reasoning when the council says a task is not complete.

## Enable Modes
1. Manual hard mode
- Set `QUENTIN_DONE_COUNCIL_STRICT_REASONING=1`.
- Effect: weak non-done reasoning triggers strict retry path and deterministic fallback reason.

2. Automatic mode (recommended)
- Brain daemon periodically reads `overview.intelligence` and auto-enters strict window when regression signals exceed thresholds.
- Auto strict env behavior:
  - active window: `QUENTIN_DONE_COUNCIL_STRICT_REASONING=1`
  - window expired: restore baseline value captured at daemon startup.

## Auto Mode Thresholds
- `QUENTIN_BRAIN_INTELLIGENCE_EVERY_SEC` (default `45`)
- `QUENTIN_BRAIN_INTELLIGENCE_STRICT_SEC` (default `180`)
- `QUENTIN_BRAIN_INTELLIGENCE_PLANNER_REPAIR_WARN` (default `0.45`)
- `QUENTIN_BRAIN_INTELLIGENCE_BLOCKED_REPEAT_WARN` (default `0.30`)
- `QUENTIN_BRAIN_INTELLIGENCE_DISCOVERY_COMPLIANCE_WARN` (default `0.80`, strict when below)
- `QUENTIN_BRAIN_INTELLIGENCE_DONE_WEAK_RESOLUTION_WARN` (default `0.50`, strict when below)

## Observability and State
- Runtime mode may show `intelligence_strict` in `guardrail_state.runtime_mode`.
- State file: `data/runtime/brain_guardrail_state.json`
  - `intelligence_strict_until`
  - `intelligence_strict_reasons`
  - `last_intelligence_eval_at`
- Event stream:
  - `brain_intelligence_strict_mode_changed` (enabled transitions)

## Rollback (False Positives)
1. Immediate rollback
- Set all strict triggers conservative, or disable auto checks:
  - `QUENTIN_BRAIN_INTELLIGENCE_EVERY_SEC=0` is not disable; it means every loop. Use high interval instead, e.g. `86400`.
  - Raise warning thresholds to avoid triggering.
- Force manual baseline:
  - `QUENTIN_DONE_COUNCIL_STRICT_REASONING=0`

2. Safe rollback procedure
- Restart daemon with adjusted env.
- Verify `guardrail_state.runtime_mode` returns to `normal`.
- Confirm `QUENTIN_DONE_COUNCIL_STRICT_REASONING` is restored to baseline.

## Verification Checklist
- Run:
  - `pytest -q tests/unit/test_brain_daemon_self_awareness_guardrails.py`
  - `pytest -q tests/unit/test_done_council_quality.py`
- Check dashboard intelligence cards for:
  - planner repair rate
  - blocked repeat ratio
  - discovery precheck compliance
  - done weak-resolution rate
