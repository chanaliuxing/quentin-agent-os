# TEST Business Failure Convergence

## Unit
- `tests/unit/test_failure_router.py`
  - verifies deterministic recovery action for:
    - `MISSING_REQUIRED_TEST`
    - `GRADER_FAILED`
    - `BUSINESS_REJECTION_UNMAPPED`
  - verifies `expected_terminal_state_for_recovery` mapping.
- `tests/unit/test_recovery_recommendation.py`
  - verifies fallback business classification no longer emits `UNCLASSIFIED_BUSINESS_FAILURE`.
- `tests/unit/test_system_metrics_report.py`
  - verifies hardening report builds with taxonomy metrics.
- `tests/unit/test_business_failure_monitor.py`
  - verifies rolling-20 trigger, ticket creation, 24h dedupe, and non-real-run filtering.
- `tests/unit/test_business_failure_signature_normalizer.py`
  - verifies stable signature normalization and taxonomy-candidate naming.
- `tests/unit/test_recovery_rollout_policy.py`
  - verifies shadow/canary/full execution decisions and eligibility.
- `tests/unit/test_harness_dossier.py`
  - verifies run dossier generation from evidence + metrics snapshots.
- `tests/unit/test_bootstrap_agent_project.py`
  - verifies skeleton bootstrap creates expected baseline files.

## Replay
- `tests/replay/test_failure_routing_replay_pack.py`
  - validates deterministic routing on replay corpus, including new business failures.
- `tests/replay/test_business_failure_golden_pack.py`
  - validates golden signature normalization and taxonomy-candidate inference.

## Control Plane
- `bash scripts/run_regression_control_plane.sh smoke`
- `bash scripts/ci_control_plane_gate.sh`
- `python scripts/run_business_failure_monitor.py`
- `python scripts/promote_business_taxonomy.py`
- `python scripts/run_recovery_canary.py`
- `python scripts/run_business_failure_goldens.py`
