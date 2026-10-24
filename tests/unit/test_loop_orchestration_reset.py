from __future__ import annotations

from quentin.cognitive.loop_orchestration import LoopRuntimeState, maybe_apply_planning_reset


def test_maybe_apply_planning_reset_triggers_on_threshold(monkeypatch) -> None:
    monkeypatch.setenv("QUENTIN_PLANNER_RESET_FAILURE_THRESHOLD", "3")
    state = LoopRuntimeState(failure_count=3, last_plan_result={"steps": [1]})
    changed = maybe_apply_planning_reset(state=state)
    assert changed is True
    assert state.last_plan_result is None
    assert "PLANNING RESET MODE" in str(state.critical_instruction or "")


def test_maybe_apply_planning_reset_not_reapplied_same_failure_count(monkeypatch) -> None:
    monkeypatch.setenv("QUENTIN_PLANNER_RESET_FAILURE_THRESHOLD", "3")
    state = LoopRuntimeState(failure_count=3, last_plan_result={"steps": [1]})
    assert maybe_apply_planning_reset(state=state) is True
    assert maybe_apply_planning_reset(state=state) is False
