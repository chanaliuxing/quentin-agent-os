from pathlib import Path

from app.control.failure_router import (
    expected_terminal_state_for_recovery,
    load_failure_router_policy,
    route_recovery_action,
)


def test_load_failure_router_policy_returns_defaults_when_missing(tmp_path: Path):
    policy = load_failure_router_policy(policy_file=tmp_path / "missing.json")
    assert "stage_actions" in policy
    assert policy["max_repeat_before_replan"] >= 1


def test_route_recovery_action_replans_for_structural_codes():
    action = route_recovery_action(
        status="failed",
        acceptance_status="rejected",
        failed_modules=["module_main"],
        replan_rounds=0,
        reviewer_codes=["PATH_CONFLICT"],
        first_failure_stage="dev_output_missing",
        failure_signature_count=1,
        max_review_loops=2,
    )
    assert action == "replan_from_spec"


def test_route_recovery_action_replans_on_repeat_signature():
    action = route_recovery_action(
        status="failed",
        acceptance_status="rejected",
        failed_modules=["module_main"],
        replan_rounds=0,
        reviewer_codes=[],
        first_failure_stage="dev_output_missing",
        failure_signature_count=2,
        max_review_loops=2,
    )
    assert action == "replan_from_spec"


def test_route_recovery_action_advances_on_passed_status():
    action = route_recovery_action(
        status="completed",
        acceptance_status="passed",
        failed_modules=[],
        replan_rounds=0,
        reviewer_codes=[],
        first_failure_stage="",
        failure_signature_count=0,
        max_review_loops=2,
    )
    assert action == "advance"


def test_route_recovery_action_uses_failure_type_actions_first():
    action = route_recovery_action(
        status="failed",
        acceptance_status="rejected",
        failed_modules=["module_main"],
        replan_rounds=0,
        reviewer_codes=[],
        failure_type="MISSING_QA_ARTIFACT",
        first_failure_stage="qa_output_missing",
        failure_signature_count=1,
        max_review_loops=2,
    )
    assert action == "replan_from_spec"


def test_route_recovery_action_non_retryable_failure_type_forces_replan():
    action = route_recovery_action(
        status="failed",
        acceptance_status="rejected",
        failed_modules=["module_main"],
        replan_rounds=0,
        reviewer_codes=[],
        failure_type="MISSING_DEV_RESULT",
        first_failure_stage="module_pipeline_failed",
        failure_signature_count=0,
        max_review_loops=2,
        policy={
            "non_retryable_failure_types": ["MISSING_DEV_RESULT"],
            "failure_type_actions": {},
            "stage_actions": {"module_pipeline_failed": {"action": "retry_same_plan", "owner": "integrator"}},
            "max_repeat_before_replan": 5,
            "structural_codes_force_replan": [],
        },
    )
    assert action == "replan_from_spec"


def test_route_recovery_action_uses_missing_required_test_template():
    action = route_recovery_action(
        status="failed",
        acceptance_status="rejected",
        failed_modules=["module_main"],
        replan_rounds=0,
        reviewer_codes=[],
        failure_type="MISSING_REQUIRED_TEST",
        first_failure_stage="required_test_missing",
        failure_signature_count=1,
        max_review_loops=2,
    )
    assert action == "replan_from_spec"


def test_route_recovery_action_retries_for_missing_planner_result_initially():
    action = route_recovery_action(
        status="failed",
        acceptance_status="rejected",
        failed_modules=["module_main"],
        replan_rounds=0,
        reviewer_codes=[],
        failure_type="MISSING_PLANNER_RESULT",
        first_failure_stage="module_pipeline_failed",
        failure_signature_count=0,
        max_review_loops=2,
    )
    assert action == "retry_same_plan"


def test_route_recovery_action_replans_for_missing_planner_result_after_repeat_limit():
    action = route_recovery_action(
        status="failed",
        acceptance_status="rejected",
        failed_modules=["module_main"],
        replan_rounds=0,
        reviewer_codes=[],
        failure_type="MISSING_PLANNER_RESULT",
        first_failure_stage="module_pipeline_failed",
        failure_signature_count=2,
        max_review_loops=2,
    )
    assert action == "replan_from_spec"


def test_route_recovery_action_uses_required_test_failed_policy():
    action = route_recovery_action(
        status="failed",
        acceptance_status="rejected",
        failed_modules=["module_main"],
        replan_rounds=0,
        reviewer_codes=[],
        failure_type="REQUIRED_TEST_FAILED",
        first_failure_stage="required_test_failed",
        failure_signature_count=1,
        max_review_loops=2,
    )
    assert action == "replan_from_spec"


def test_route_recovery_action_sends_business_unmapped_to_taxonomy_review():
    action = route_recovery_action(
        status="failed",
        acceptance_status="rejected",
        failed_modules=[],
        replan_rounds=0,
        reviewer_codes=[],
        failure_type="BUSINESS_REJECTION_UNMAPPED",
        first_failure_stage="unclassified_failure",
        failure_signature_count=1,
        max_review_loops=2,
    )
    assert action == "taxonomy_review_required"


def test_expected_terminal_state_for_recovery_map():
    state = expected_terminal_state_for_recovery(
        failure_type="GRADER_FAILED",
        recovery_action="replan_from_spec",
    )
    assert state == "REJECTED"


def test_expected_terminal_state_for_missing_planner_retry_map():
    state = expected_terminal_state_for_recovery(
        failure_type="MISSING_PLANNER_RESULT",
        recovery_action="retry_same_plan",
    )
    assert state == "REJECTED"


def test_route_recovery_action_new_agent_execution_subtype():
    action = route_recovery_action(
        status="failed",
        acceptance_status="rejected",
        failed_modules=["module_main"],
        replan_rounds=0,
        reviewer_codes=[],
        failure_type="AGENT_RESULT_PARSE_FAILED",
        first_failure_stage="qa_contract_failed",
        failure_signature_count=1,
        max_review_loops=2,
    )
    assert action == "replan_from_spec"


def test_expected_terminal_state_for_new_agent_execution_subtype():
    state = expected_terminal_state_for_recovery(
        failure_type="AGENT_SUBPROCESS_NONZERO_EXIT",
        recovery_action="replan_from_spec",
    )
    assert state == "REJECTED"


def test_route_recovery_action_uses_stage_override_for_subprocess_planner():
    action = route_recovery_action(
        status="failed",
        acceptance_status="rejected",
        failed_modules=["module_main"],
        replan_rounds=0,
        reviewer_codes=[],
        failure_type="AGENT_SUBPROCESS_NONZERO_EXIT",
        first_failure_stage="planner",
        failure_signature_count=0,
        max_review_loops=2,
    )
    assert action == "retry_same_plan"


def test_route_recovery_action_uses_stage_override_from_handoff_stage_name():
    action = route_recovery_action(
        status="failed",
        acceptance_status="rejected",
        failed_modules=["module_main"],
        replan_rounds=0,
        reviewer_codes=[],
        failure_type="AGENT_SUBPROCESS_NONZERO_EXIT",
        first_failure_stage="planner_handoff_failed",
        failure_signature_count=0,
        max_review_loops=2,
    )
    assert action == "retry_same_plan"
