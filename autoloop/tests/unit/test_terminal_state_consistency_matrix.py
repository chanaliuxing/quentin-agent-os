import pytest

from app.temporal.workflow import _derive_failure_diagnostics, _derive_terminal_state


@pytest.mark.parametrize(
    "scenario,events,acceptance_status,recommended_action,expected_primary,expected_terminal",
    [
        (
            "path_conflict",
            [
                {
                    "event_id": "wf.phase.reviewer.001",
                    "event_time": "2026-03-08T00:00:00Z",
                    "failure_type": "PATH_CONFLICT",
                    "stage": "reviewer",
                    "actor": "activity",
                    "cause_class": "business",
                }
            ],
            "rejected",
            "replan_from_spec",
            "PATH_CONFLICT",
            "REJECTED",
        ),
        (
            "missing_required_test",
            [
                {
                    "event_id": "wf.phase.qa.001",
                    "event_time": "2026-03-08T00:00:00Z",
                    "failure_type": "MISSING_REQUIRED_TEST",
                    "stage": "required_test_missing",
                    "actor": "activity",
                    "cause_class": "contract",
                }
            ],
            "rejected",
            "replan_from_spec",
            "MISSING_REQUIRED_TEST",
            "REJECTED",
        ),
        (
            "grader_failed",
            [
                {
                    "event_id": "wf.phase.qa.002",
                    "event_time": "2026-03-08T00:00:01Z",
                    "failure_type": "GRADER_FAILED",
                    "stage": "grader_failed",
                    "actor": "activity",
                    "cause_class": "business",
                }
            ],
            "rejected",
            "replan_from_spec",
            "GRADER_FAILED",
            "REJECTED",
        ),
        (
            "business_unmapped",
            [
                {
                    "event_id": "wf.phase.workflow.003",
                    "event_time": "2026-03-08T00:00:02Z",
                    "failure_type": "BUSINESS_REJECTION_UNMAPPED",
                    "stage": "unclassified_failure",
                    "actor": "workflow",
                    "cause_class": "business",
                }
            ],
            "rejected",
            "taxonomy_review_required",
            "BUSINESS_REJECTION_UNMAPPED",
            "REJECTED",
        ),
        (
            "state_db_degraded",
            [
                {
                    "event_id": "wf.phase.runner.001",
                    "event_time": "2026-03-08T00:00:00Z",
                    "failure_type": "STATE_DB_DEGRADED",
                    "stage": "dev",
                    "actor": "activity",
                    "cause_class": "environment",
                }
            ],
            "rejected",
            "escalate_to_human",
            "STATE_DB_DEGRADED",
            "ABORTED",
        ),
        (
            "global_timeout",
            [
                {
                    "event_id": "wf.phase.dev.001",
                    "event_time": "2026-03-08T00:00:00Z",
                    "failure_type": "GLOBAL_TIMEOUT",
                    "stage": "dev",
                    "actor": "activity",
                    "cause_class": "execution",
                }
            ],
            "rejected",
            "replan_from_spec",
            "GLOBAL_TIMEOUT",
            "TIMEOUT",
        ),
    ],
)
def test_terminal_state_consistency_matrix(
    scenario: str,
    events: list[dict],
    acceptance_status: str,
    recommended_action: str,
    expected_primary: str,
    expected_terminal: str,
):
    diagnostics = _derive_failure_diagnostics(
        results={},
        test_results={"status": "failed", "acceptance_status": acceptance_status},
        failed_modules=[],
        events=events,
    )
    terminal_state = _derive_terminal_state(
        acceptance_status=acceptance_status,
        recommended_action=recommended_action,
        failure_diagnostics=diagnostics,
    )
    assert diagnostics["primary_failure_type"] == expected_primary, scenario
    assert terminal_state == expected_terminal, scenario
