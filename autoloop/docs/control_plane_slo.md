# Control Plane SLO

## Release Gates
- `primary_failure_hit_rate = 1.0`
- `event_completeness_rate = 1.0`
- `terminal_state_consistency_rate = 1.0`
- `unknown_failure_rate = 0.0`
- `required_test_failure_detail_missing_rate = 0.0`

## Metric Definitions
- `primary_failure_hit_rate`: ratio of scenarios where derived `primary_failure_type` matches expected value in control-plane matrix report.
- `event_completeness_rate`: ratio of terminal runs containing required lifecycle events (`WORKFLOW_STARTED`, `WORKFLOW_TERMINATED`).
- `terminal_state_consistency_rate`: ratio of primary-failure buckets mapped to a single stable terminal state.
- `unknown_failure_rate`: ratio of execution summaries with unknown/empty primary failure type.
- `required_test_failure_detail_missing_rate`: ratio of `REQUIRED_TEST_FAILED` runs that miss structured detail contract (`required_test=...`, `failure_type=...`, `location=...`).

## Hard Rules
- If a run reaches terminal state but lacks `WORKFLOW_TERMINATED`, mark `MISSING_TERMINAL_EVENT` and fail event completeness gate.
- `primary_failure_type` must never persist as `NONE/UNKNOWN/NULL`; it is normalized to:
  - `UNCLASSIFIED_BUSINESS_FAILURE`
  - `UNCLASSIFIED_EXECUTION_FAILURE`
  - `UNCLASSIFIED_ENVIRONMENT_FAILURE`
- Any `REQUIRED_TEST_FAILED` run without structured required-test details is classified as control-plane defect via:
  - `UNKNOWN_REQUIRED_TEST_FAILURE`
  - `CONTROL_PLANE_MISSING_FAILURE_DETAIL`

## Commands
- `python scripts/run_control_plane_matrix.py`
- `python scripts/run_control_plane_slo.py`
- `python scripts/run_control_plane_slo_split.py`
- `python scripts/repair_missing_terminal_events.py`
- `bash scripts/ci_control_plane_gate.sh`
- `bash scripts/run_regression_control_plane.sh smoke`
- `bash scripts/run_regression_control_plane.sh extended`

## Output Artifacts
- `runtime/metrics/control_plane_matrix_report.json`
- `runtime/metrics/control_plane_slo_report.json`
- `runtime/metrics/control_plane_slo_split_report.json`
