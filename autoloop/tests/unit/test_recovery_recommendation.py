from app.config import settings
from app.temporal.workflow import (
    _apply_failure_circuit_breaker,
    _derive_failure_diagnostics,
    _derive_terminal_state,
    _enforce_acceptance_from_pipeline_outcome,
    _recommend_recovery_action,
)


def test_recommend_recovery_action_returns_advance_on_success():
    action = _recommend_recovery_action(
        status="completed",
        acceptance_status="passed",
        failed_modules=[],
        replan_rounds=0,
    )
    assert action == "advance"


def test_derive_failure_diagnostics_clears_primary_on_acceptance_passed():
    diagnostics = _derive_failure_diagnostics(
        results={},
        test_results={"status": "completed", "acceptance_status": "passed", "failure_types": ["GRADER_FAILED"]},
        failed_modules=[],
        events=[
            {
                "event_id": "wf.phase.qa.001",
                "event_time": "2026-03-08T00:00:00Z",
                "failure_type": "GRADER_FAILED",
                "stage": "grader_failed",
                "actor": "activity",
            }
        ],
    )
    assert diagnostics["primary_failure_type"] == ""
    assert diagnostics["secondary_failure_types"] == []
    assert diagnostics["failure_events"] == []
    assert diagnostics["final_status_label"] == "ACCEPTED"


def test_recommend_recovery_action_returns_retry_for_failed_modules():
    action = _recommend_recovery_action(
        status="failed",
        acceptance_status="rejected",
        failed_modules=["module_main"],
        replan_rounds=0,
    )
    assert action == "retry_same_plan"


def test_recommend_recovery_action_returns_replan_without_failed_modules():
    action = _recommend_recovery_action(
        status="failed",
        acceptance_status="rejected",
        failed_modules=[],
        replan_rounds=1,
    )
    assert action == "replan_from_spec"


def test_recommend_recovery_action_switches_to_replan_after_retry_budget(monkeypatch):
    monkeypatch.setattr(settings, "max_review_loops_per_module", 2)
    action = _recommend_recovery_action(
        status="failed",
        acceptance_status="rejected",
        failed_modules=["module_main"],
        replan_rounds=2,
    )
    assert action == "replan_from_spec"


def test_recommend_recovery_action_uses_failure_stage_routing():
    action = _recommend_recovery_action(
        status="failed",
        acceptance_status="rejected",
        failed_modules=["module_main"],
        replan_rounds=0,
        first_failure_stage="required_test_missing",
    )
    assert action == "replan_from_spec"


def test_enforce_acceptance_from_pipeline_outcome_rejects_when_pipeline_failed():
    updated, acceptance = _enforce_acceptance_from_pipeline_outcome(
        test_results={
            "status": "success",
            "acceptance_status": "passed",
            "execution_status": "tests_passed",
            "failure_types": [],
        },
        failed_modules=[{"name": "module_main"}],
        missing_results=False,
    )
    assert acceptance == "rejected"
    assert updated["acceptance_status"] == "rejected"
    assert updated["status"] == "failed"
    assert updated["execution_status"] == "pipeline_failed"
    assert "MODULE_PIPELINE_FAILED" in updated["failure_types"]


def test_enforce_acceptance_from_pipeline_outcome_keeps_passed_when_no_pipeline_failure():
    updated, acceptance = _enforce_acceptance_from_pipeline_outcome(
        test_results={
            "status": "success",
            "acceptance_status": "passed",
            "execution_status": "tests_passed",
            "failure_types": [],
        },
        failed_modules=[],
        missing_results=False,
    )
    assert acceptance == "passed"
    assert updated["acceptance_status"] == "passed"
    assert updated["status"] == "success"


def test_recommend_recovery_action_prioritizes_structural_reviewer_codes():
    action = _recommend_recovery_action(
        status="failed",
        acceptance_status="rejected",
        failed_modules=["module_main"],
        replan_rounds=0,
        reviewer_codes=["PATH_CONFLICT"],
    )
    assert action == "replan_from_spec"


def test_recommend_recovery_action_prioritizes_failure_type_policy():
    action = _recommend_recovery_action(
        status="failed",
        acceptance_status="rejected",
        failed_modules=["module_main"],
        replan_rounds=0,
        failure_type="MISSING_DEV_RESULT",
        first_failure_stage="module_pipeline_failed",
    )
    assert action == "replan_from_spec"


def test_derive_failure_diagnostics_prefers_missing_agent_output():
    diagnostics = _derive_failure_diagnostics(
        results={
            "module_main": {
                "planner": "{}",
                "reviewer": "{}",
                "dev": "No result file found",
                "qa": "No result file found",
            }
        },
        test_results={"missing_required_tests": [], "grader_results": {}},
        failed_modules=[],
    )
    assert diagnostics["first_failure_stage"] == "dev_output_missing"
    assert diagnostics["owner_agent"] == "dev"
    assert diagnostics["primary_failure_type"] == "MISSING_DEV_RESULT"
    assert diagnostics["failure_signature"] == "dev_output_missing:module_main"


def test_apply_failure_circuit_breaker_forces_replan_on_repeat_signature():
    action = _apply_failure_circuit_breaker(
        recommended_action="retry_same_plan",
        failure_signature="qa_output_missing:module_main",
        failure_signature_counts={"qa_output_missing:module_main": 2},
    )
    assert action == "replan_from_spec"


def test_derive_failure_diagnostics_prefers_acceptance_failure_types():
    diagnostics = _derive_failure_diagnostics(
        results={
            "module_main": {
                "planner": "{}",
                "reviewer": "{}",
                "dev": "{}",
                "qa": "{}",
            }
        },
        test_results={
            "missing_required_tests": [],
            "grader_results": {"contract_validator": "fail"},
            "failure_types": ["MISSING_QA_ARTIFACT"],
        },
        failed_modules=[],
    )
    assert diagnostics["primary_failure_type"] == "MISSING_QA_ARTIFACT"
    assert diagnostics["first_failure_stage"] == "acceptance_contract_failed"


def test_derive_failure_diagnostics_distinguishes_failed_required_tests_from_missing_binding():
    diagnostics = _derive_failure_diagnostics(
        results={
            "module_main": {
                "planner": "{}",
                "reviewer": "{}",
                "dev": "{}",
                "qa": "{}",
            }
        },
        test_results={
            "missing_required_tests": [],
            "failed_required_tests": ["unit"],
            "grader_results": {},
            "failure_types": ["REQUIRED_TEST_FAILED"],
        },
        failed_modules=[],
    )
    assert diagnostics["primary_failure_type"] == "REQUIRED_TEST_FAILED"
    assert diagnostics["first_failure_stage"] == "acceptance_contract_failed"


def test_derive_failure_diagnostics_includes_grader_detail_in_signature():
    diagnostics = _derive_failure_diagnostics(
        results={
            "module_main": {
                "planner": "{}",
                "reviewer": "{}",
                "dev": "{}",
                "qa": "{}",
            }
        },
        test_results={
            "missing_required_tests": [],
            "failed_required_tests": [],
            "grader_results": {"contract_validator": "fail"},
            "grader_details": {
                "contract_validator": [
                    {"failure_type": "INVALID_DEV_CONTRACT", "error": "contract_validation_failed"}
                ]
            },
            "failure_types": [],
        },
        failed_modules=[],
    )
    assert diagnostics["primary_failure_type"] == "GRADER_FAILED"
    assert diagnostics["failure_signature"] == "grader_failed:contract_validator:INVALID_DEV_CONTRACT"


def test_derive_failure_diagnostics_prioritizes_business_contract_codes_over_runner_blocked():
    diagnostics = _derive_failure_diagnostics(
        results={
            "module_main": {
                "planner": "{}",
                "reviewer": '{"verdict":"needs_revision","finding_codes":["PATH_CONFLICT","MISSING_TEST_BINDING"]}',
                "dev": '{"status":"failed","implementation_notes":"runner_blocked"}',
                "qa": "{}",
            }
        },
        test_results={"failure_types": ["RUNNER_BLOCKED"], "missing_required_tests": [], "grader_results": {}},
        failed_modules=[],
    )
    assert diagnostics["primary_failure_type"] == "PATH_CONFLICT"
    assert "RUNNER_BLOCKED" in diagnostics["secondary_failure_types"]
    assert diagnostics["final_status_label"] == "RUNNER_BLOCKED"


def test_derive_failure_diagnostics_sets_final_status_from_execution_timeout():
    diagnostics = _derive_failure_diagnostics(
        results={"module_main": {"planner": "{}", "reviewer": "{}", "dev": "{}", "qa": "{}"}},
        test_results={
            "status": "failed",
            "execution_status": "global_timeout",
            "acceptance_status": "rejected",
            "failure_types": [],
            "missing_required_tests": [],
            "grader_results": {},
        },
        failed_modules=[{"name": "module_main"}],
    )
    assert diagnostics["final_status_label"] == "GLOBAL_TIMEOUT"


def test_derive_failure_diagnostics_prefers_handoff_mismatch_over_timeout_for_primary():
    diagnostics = _derive_failure_diagnostics(
        results={"module_main": {"planner": "{}", "reviewer": "{}", "dev": "{}", "qa": "{}"}},
        test_results={
            "status": "failed",
            "execution_status": "global_timeout",
            "acceptance_status": "rejected",
            "failure_types": [],
            "missing_required_tests": [],
            "grader_results": {},
        },
        failed_modules=[{"name": "module_main"}],
        module_failure_details=[
            {
                "module_name": "module_main",
                "failure_type": "DEV_HANDOFF_STATE_MISMATCH",
                "stage": "dev_handoff_failed",
                "owner_agent": "dev",
                "first_failure_at": "2026-03-23T20:00:00Z",
            }
        ],
    )
    assert diagnostics["primary_failure_type"] == "DEV_HANDOFF_STATE_MISMATCH"
    assert diagnostics["final_status_label"] == "GLOBAL_TIMEOUT"
    assert diagnostics["secondary_failure_types"] == []


def test_derive_failure_diagnostics_prefers_handoff_mismatch_over_timeout_with_event_stream():
    diagnostics = _derive_failure_diagnostics(
        results={"module_main": {"planner": "{}", "reviewer": "{}", "dev": "{}", "qa": "{}"}},
        test_results={
            "status": "failed",
            "execution_status": "global_timeout",
            "acceptance_status": "rejected",
            "failure_types": [],
            "missing_required_tests": [],
            "grader_results": {},
        },
        failed_modules=[{"name": "module_main"}],
        module_failure_details=[
            {
                "module_name": "module_main",
                "failure_type": "QA_HANDOFF_STATE_MISMATCH",
                "stage": "qa_handoff_failed",
                "owner_agent": "qa",
                "first_failure_at": "2026-03-23T20:00:00Z",
            }
        ],
        events=[
            {
                "event_id": "wf.phase.timeout.001",
                "event_time": "2026-03-23T21:00:00Z",
                "failure_type": "GLOBAL_TIMEOUT",
                "stage": "workflow",
                "actor": "workflow",
            }
        ],
    )
    assert diagnostics["primary_failure_type"] == "QA_HANDOFF_STATE_MISMATCH"
    assert diagnostics["final_status_label"] == "GLOBAL_TIMEOUT"
    assert "GLOBAL_TIMEOUT" in diagnostics["secondary_failure_types"]


def test_derive_failure_diagnostics_emits_failure_events():
    diagnostics = _derive_failure_diagnostics(
        results={
            "module_main": {
                "planner": "{}",
                "reviewer": '{"verdict":"needs_revision","finding_codes":["MISSING_TEST_BINDING"]}',
                "dev": "{}",
                "qa": "{}",
            }
        },
        test_results={"failure_types": [], "missing_required_tests": [], "grader_results": {}},
        failed_modules=[],
    )
    events = diagnostics["failure_events"]
    assert events
    assert events[0]["cause_type"] == "MISSING_TEST_BINDING"
    assert events[0]["cause_class"] == "business"
    assert events[0]["event_time"]
    assert "payload" in events[0]


def test_derive_terminal_state_maps_timeout_to_timeout():
    terminal = _derive_terminal_state(
        acceptance_status="rejected",
        recommended_action="replan_from_spec",
        failure_diagnostics={
            "primary_failure_type": "PATH_CONFLICT",
            "secondary_failure_types": ["GLOBAL_TIMEOUT"],
            "final_status_label": "GLOBAL_TIMEOUT",
        },
    )
    assert terminal == "TIMEOUT"


def test_derive_failure_diagnostics_never_returns_none_primary():
    diagnostics = _derive_failure_diagnostics(
        results={},
        test_results={"status": "failed", "acceptance_status": "rejected"},
        failed_modules=[],
        events=[
            {
                "event_id": "wf.phase.workflow.001",
                "event_time": "2026-03-08T00:00:00Z",
                "failure_type": None,
                "stage": "workflow",
                "actor": "workflow",
            }
        ],
    )
    assert diagnostics["primary_failure_type"] == "BUSINESS_REJECTION_UNMAPPED"
    assert diagnostics["failure_events"]


def test_derive_failure_diagnostics_keeps_module_failure_payload():
    diagnostics = _derive_failure_diagnostics(
        results={"module_main": {"planner": "{}", "reviewer": "{}", "dev": "{}", "qa": "{}"}},
        test_results={
            "status": "failed",
            "execution_status": "tests_failed",
            "acceptance_status": "rejected",
            "failure_types": [],
            "missing_required_tests": [],
            "grader_results": {},
        },
        failed_modules=[{"name": "module_main"}],
        module_failure_details=[
            {
                "module_name": "module_main",
                "failure_type": "AGENT_SUBPROCESS_NONZERO_EXIT",
                "stage": "dev_handoff_failed",
                "owner_agent": "dev",
                "first_failure_at": "2026-04-01T00:00:00Z",
                "payload": {
                    "failure_detail": {
                        "exit_code": 2,
                        "execution_mode": "resume",
                        "stderr_tail": "traceback tail",
                    }
                },
            }
        ],
    )
    assert diagnostics["primary_failure_type"] == "AGENT_SUBPROCESS_NONZERO_EXIT"
    assert diagnostics["failure_events"]
    event = diagnostics["failure_events"][0]
    assert event["stage"] == "dev_handoff_failed"
    assert event["payload"]["failure_detail"]["exit_code"] == 2


def test_derive_failure_diagnostics_uses_event_stage_for_primary_stage():
    diagnostics = _derive_failure_diagnostics(
        results={},
        test_results={"status": "failed", "acceptance_status": "rejected"},
        failed_modules=[],
        events=[
            {
                "event_id": "wf.phase.planner.001",
                "event_time": "2026-04-01T00:00:00Z",
                "failure_type": "AGENT_SUBPROCESS_NONZERO_EXIT",
                "stage": "planner",
                "actor": "planner",
                "payload": {"subprocess_detail": {"exit_code": 2}},
            }
        ],
    )
    assert diagnostics["primary_failure_type"] == "AGENT_SUBPROCESS_NONZERO_EXIT"
    assert diagnostics["first_failure_stage"] == "planner"
    assert diagnostics["owner_agent"] == "planner"
