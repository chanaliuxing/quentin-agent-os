from __future__ import annotations

from quentin.cognitive.planning_payload_matrix import derive_planner_lifecycle_payload


def test_planning_payload_matrix_initial_stage() -> None:
    payload = derive_planner_lifecycle_payload(
        context={"attempt_index": 1, "failure_count": 0, "tool_only_no_update_count": 0}
    )
    assert payload.stage == "initial"
    assert payload.attempt_band == "early"
    assert payload.force_speculative_execution is False


def test_planning_payload_matrix_retry_stage() -> None:
    payload = derive_planner_lifecycle_payload(
        context={"attempt_index": 2, "failure_count": 1, "tool_only_no_update_count": 0}
    )
    assert payload.stage == "retry"


def test_planning_payload_matrix_stuck_stage_enables_speculative() -> None:
    payload = derive_planner_lifecycle_payload(
        context={
            "attempt_index": 3,
            "failure_count": 3,
            "tool_only_no_update_count": 2,
            "last_attempt_evaluation": {"category": "logic_path_error"},
        }
    )
    assert payload.stage == "stuck"
    assert payload.force_speculative_execution is True


def test_planning_payload_matrix_forces_progress_sync_after_tool_feedback_turns() -> None:
    payload = derive_planner_lifecycle_payload(
        context={
            "attempt_index": 4,
            "failure_count": 2,
            "tool_only_no_update_count": 3,
            "last_attempt_evaluation": {"category": "logic_path_error"},
        }
    )
    assert payload.stage == "stuck"
    assert payload.force_progress_sync is True


def test_planning_payload_matrix_late_retry_escalation() -> None:
    payload = derive_planner_lifecycle_payload(
        context={"attempt_index": 5, "failure_count": 1, "tool_only_no_update_count": 0}
    )
    assert payload.stage == "retry"
    assert payload.attempt_band == "late"
    assert payload.force_progress_sync is True


def test_planning_payload_matrix_misalignment_enters_stuck() -> None:
    payload = derive_planner_lifecycle_payload(
        context={
            "attempt_index": 3,
            "failure_count": 1,
            "tool_only_no_update_count": 1,
            "last_attempt_evaluation": {"category": "plan_execution_misalignment"},
        }
    )
    assert payload.stage == "stuck"
