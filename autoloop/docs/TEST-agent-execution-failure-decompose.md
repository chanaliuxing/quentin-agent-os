# TEST: Agent Execution Failure Decomposition

## Unit
- `pytest tests/unit/test_agent_execution_failure_taxonomy.py -q`
- `pytest tests/unit/test_agent_execution_failure_breakdown.py -q`
- `pytest tests/unit/test_failure_router.py -q`
- `pytest tests/unit/test_recovery_recommendation.py tests/unit/test_terminal_state_consistency_matrix.py -q`

## Replay Goldens
- `pytest tests/replay/test_agent_execution_failure_golden_pack.py -q`
- `python scripts/run_business_failure_goldens.py`

## Runtime Metrics
- `python scripts/run_agent_execution_failure_breakdown.py --window-size 20`
- `python scripts/run_recovery_canary.py --window-size 50`
- Validate output file:
  - `runtime/metrics/agent_execution_failure_breakdown_report.json`
  - `runtime/metrics/recovery_canary_report.json` (`top2_execution_subtype_terminal_match`)
