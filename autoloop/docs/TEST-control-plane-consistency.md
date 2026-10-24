# TEST: Control-Plane Consistency

## Scope
- Terminal-state consistency across canonical failure scenarios.
- Failure-event completeness for primary-cause diagnostics.

## Commands
- `pytest tests/unit/test_terminal_state_consistency_matrix.py -q`
- `python scripts/run_control_plane_matrix.py`

## Expected
- Matrix unit tests pass for:
  - `PATH_CONFLICT -> REJECTED`
  - `MISSING_REQUIRED_TEST -> REJECTED`
  - `STATE_DB_DEGRADED -> ABORTED`
  - `GLOBAL_TIMEOUT -> TIMEOUT`
- `runtime/metrics/control_plane_matrix_report.json` exists.
- Report pass rate is `1.0` for `terminal_state_consistency`.
- Every scenario shows event completeness rate `1.0`.
