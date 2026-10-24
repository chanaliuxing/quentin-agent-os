from app.control.recovery_rollout_policy import (
    evaluate_recovery_rollout,
    load_recovery_rollout_policy,
)


def test_recovery_rollout_shadow_mode_does_not_execute(tmp_path):
    policy = load_recovery_rollout_policy(policy_file=tmp_path / "missing.json")
    result = evaluate_recovery_rollout(
        policy=policy,
        project_id="real-001",
        phase_id="phase_01",
        action="replan_from_spec",
        primary_failure_type="MISSING_REQUIRED_TEST",
        acceptance_status="rejected",
        retry_count=0,
    )
    assert result["execute"] is False
    assert result["shadow"] is True


def test_recovery_rollout_canary_mode_is_deterministic():
    policy = {
        "mode": "canary",
        "canary_percentage": 100,
        "actions": {"replan_from_spec": {"max_retry_budget": 2}},
    }
    result = evaluate_recovery_rollout(
        policy=policy,
        project_id="real-002",
        phase_id="phase_01",
        action="replan_from_spec",
        primary_failure_type="MISSING_REQUIRED_TEST",
        acceptance_status="rejected",
        retry_count=0,
    )
    assert result["execute"] is True
    assert result["reason"] == "canary_selected"


def test_recovery_rollout_taxonomy_requires_business_failure():
    policy = {
        "mode": "full",
        "actions": {"taxonomy_review_required": {"max_retry_budget": 1}},
    }
    blocked = evaluate_recovery_rollout(
        policy=policy,
        project_id="real-003",
        phase_id="phase_01",
        action="taxonomy_review_required",
        primary_failure_type="MISSING_REQUIRED_TEST",
        acceptance_status="rejected",
        retry_count=0,
    )
    allowed = evaluate_recovery_rollout(
        policy=policy,
        project_id="real-003",
        phase_id="phase_01",
        action="taxonomy_review_required",
        primary_failure_type="BUSINESS_REJECTION_UNMAPPED",
        acceptance_status="rejected",
        retry_count=0,
    )
    assert blocked["execute"] is False
    assert allowed["execute"] is True
