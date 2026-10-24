from __future__ import annotations

from quentin.cognitive.planning_retry_delta import derive_retry_plan_delta


def test_retry_plan_delta_not_generated_on_first_attempt() -> None:
    delta = derive_retry_plan_delta(
        attempt_index=1,
        previous_plan_steps=[{"step_id": "s1", "description": "d"}],
        last_exec_result={},
    )
    assert delta is None


def test_retry_plan_delta_contains_patch_for_retry() -> None:
    delta = derive_retry_plan_delta(
        attempt_index=2,
        previous_plan_steps=[{"step_id": "s1", "description": "write"}, {"step_id": "s2", "description": "verify"}],
        last_exec_result={
            "raw": {"error": "timeout"},
            "attempt_evaluation": {"category": "environment_timeout_error"},
        },
    )
    assert delta is not None
    assert delta.previous_step_count == 2
    assert "RETRY PLAN DELTA" in str(delta.prompt_patch or "")
