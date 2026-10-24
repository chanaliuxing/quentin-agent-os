# ACCEPTANCE Business Failure Convergence

## Acceptance Criteria
- Recovery routing is deterministic for `MISSING_REQUIRED_TEST` and `GRADER_FAILED`.
- Legacy `UNCLASSIFIED_BUSINESS_FAILURE` is promoted to explicit business enums in diagnostics path.
- Unmapped business failures route to `taxonomy_review_required` and keep terminal state consistency.
- Failure-to-recovery mapping table remains aligned with runtime policy and tests.

## Release Gate
- `bash scripts/ci_control_plane_gate.sh` passes.
- `pytest tests/unit/test_failure_router.py -q` passes.
- `pytest tests/replay/test_failure_routing_replay_pack.py -q` passes.
- `pytest tests/unit/test_business_failure_monitor.py -q` passes.
- `pytest tests/unit/test_recovery_rollout_policy.py -q` passes.
- `pytest tests/replay/test_business_failure_golden_pack.py -q` passes.
- `python scripts/run_business_failure_monitor.py` writes monitor report; when threshold hit, creates one taxonomy ticket.
- `python scripts/promote_business_taxonomy.py` writes promotion candidates.
- `python scripts/run_recovery_canary.py` writes canary report.

## Operational Target
- Rolling 20-run ratio for `BUSINESS_REJECTION_UNMAPPED` < 5%.
- Ticket dedupe rule: same `target_failure_type + normalized_signature` creates at most one ticket per 24h.
