# TEST - Failure Semantics Regression

## Unit Tests
- `pytest tests/unit/test_failure_router.py -q`
- `pytest tests/unit/test_recovery_recommendation.py -q`
- `pytest tests/unit/test_acceptance_gate.py -q`
- `pytest tests/unit/test_run_agent_failure_contract.py -q`
- `pytest tests/unit/test_contract_schemas.py -q`

## Integration Tests
- `pytest tests/integration/test_workflow.py::test_temporal_mock_workflow -q`

## Replay Tests
- `pytest tests/replay/test_failure_routing_replay_pack.py -q`

## Policy Diagnosis CLI
- `python -m app.main diagnose-recovery --status failed --acceptance-status rejected --failure-type MISSING_DEV_RESULT --first-failure-stage dev_output_missing --failed-modules module_main`

## Full Gate
- `./scripts/ci_gate.sh`

## Scenario Matrix (Manual/Automation)
- `MISSING_DEV_RESULT` -> expected `replan_from_spec`
- `MISSING_QA_RESULT` -> expected `replan_from_spec`
- `INVALID_DEV_CONTRACT` -> expected `acceptance=rejected`
- `STATE_DB_DEGRADED` (strict mode on) -> expected `acceptance=rejected`
- `MISSING_DEV_ARTIFACT` -> expected `soft_fail + failure_type=MISSING_DEV_ARTIFACT`
- `MISSING_QA_ARTIFACT` -> expected `soft_fail + failure_type=MISSING_QA_ARTIFACT`
