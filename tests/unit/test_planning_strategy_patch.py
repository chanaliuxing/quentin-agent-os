from __future__ import annotations

from quentin.cognitive.planning_strategy_patch import derive_planning_strategy_patch


def test_planning_strategy_patch_timeout_category() -> None:
    patch = derive_planning_strategy_patch(
        context={
            "planner_lifecycle_payload": {"stage": "retry"},
            "last_attempt_evaluation": {"category": "environment_timeout_error"},
        }
    )
    assert patch is not None
    assert patch.category == "environment_timeout_error"
    assert "timeout" in str(patch.prompt_patch or "").lower()


def test_planning_strategy_patch_plan_execution_misalignment_category() -> None:
    patch = derive_planning_strategy_patch(
        context={
            "planner_lifecycle_payload": {"stage": "retry"},
            "last_attempt_evaluation": {"category": "plan_execution_misalignment"},
        }
    )
    assert patch is not None
    assert patch.patch_id == "tool_alignment_enforcement_v1"


def test_planning_strategy_patch_respects_target_filter(monkeypatch) -> None:
    monkeypatch.setenv("QUENTIN_PLANNER_STRATEGY_PATCH_TARGETS", "tool_execution_error")
    monkeypatch.setenv("QUENTIN_PLANNER_STRATEGY_PATCH_FALLBACK_ENABLED", "0")
    patch = derive_planning_strategy_patch(
        context={
            "planner_lifecycle_payload": {"stage": "retry"},
            "last_attempt_evaluation": {"category": "environment_timeout_error"},
        }
    )
    assert patch is None


def test_planning_strategy_patch_fallback_for_stuck_unknown(monkeypatch) -> None:
    monkeypatch.setenv("QUENTIN_PLANNER_STRATEGY_PATCH_TARGETS", "none")
    monkeypatch.setenv("QUENTIN_PLANNER_STRATEGY_PATCH_FALLBACK_ENABLED", "1")
    patch = derive_planning_strategy_patch(
        context={
            "planner_lifecycle_payload": {"stage": "stuck"},
            "last_attempt_evaluation": {"category": "unknown_new_error"},
        }
    )
    assert patch is not None
    assert patch.patch_id == "generic_retry_replan_v1"


def test_planning_strategy_patch_applies_subcategory_overlay() -> None:
    patch = derive_planning_strategy_patch(
        context={
            "planner_lifecycle_payload": {"stage": "retry"},
            "last_attempt_evaluation": {
                "category": "tool_execution_error",
                "error_subcategory": "browser_selector_not_found",
            },
        }
    )
    assert patch is not None
    assert "selector_probe" in list(patch.required_prechecks or [])


def test_planning_strategy_patch_applies_tool_alignment_overlay() -> None:
    patch = derive_planning_strategy_patch(
        context={
            "planner_lifecycle_payload": {"stage": "retry"},
            "last_attempt_evaluation": {
                "category": "tool_execution_error",
                "error_subcategory": "plan_execution_misalignment",
            },
        }
    )
    assert patch is not None
    assert "tool_alignment_check" in list(patch.required_prechecks or [])
