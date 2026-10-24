from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from quentin.cognitive.loop_impl import CognitiveLoop, CognitiveTask


def _make_loop() -> CognitiveLoop:
    loop = CognitiveLoop.__new__(CognitiveLoop)
    loop.repo_root = Path(".").resolve()
    return loop


def test_subagent_uses_minimal_mode_in_planner_prompt(monkeypatch) -> None:
    monkeypatch.setenv("QUENTIN_FF_PROMPT_MIGRATION_M1_SYSTEM_FACTORY", "1")
    loop = _make_loop()
    goal = SimpleNamespace(goal_id="g-sub", metadata={})
    prompt = loop._build_planner_question_prompt(
        goal=goal,
        task_text="do task",
        plan_schema_text='{"steps":[...]}',
        skill_suggestions=[{"skill_id": "skill.one", "description": "desc"}],
        context={"is_subagent": True},
    )
    assert "Runtime: agent=quentin-cognitive-loop" in prompt
    assert "Tools (short summaries):" not in prompt
    assert "Skills:" not in prompt
    assert "Memory:" not in prompt


def test_parent_keeps_full_mode_in_planner_prompt(monkeypatch) -> None:
    monkeypatch.setenv("QUENTIN_FF_PROMPT_MIGRATION_M1_SYSTEM_FACTORY", "1")
    loop = _make_loop()
    goal = SimpleNamespace(goal_id="g-parent", metadata={})
    prompt = loop._build_planner_question_prompt(
        goal=goal,
        task_text="do task",
        plan_schema_text='{"steps":[...]}',
        skill_suggestions=[{"skill_id": "skill.one", "description": "desc"}],
        context={"is_subagent": False},
    )
    assert "Tools (short summaries):" in prompt


def test_subagent_uses_minimal_mode_in_executor_prompt(monkeypatch) -> None:
    monkeypatch.setenv("QUENTIN_FF_PROMPT_MIGRATION_M1_SYSTEM_FACTORY", "1")
    loop = _make_loop()
    task = CognitiveTask(input_text="x", metadata={"is_subagent": True})
    goal = SimpleNamespace(goal_id="g-exec", metadata={})
    ctx = loop._build_executor_prompt_context(task=task, goal=goal, progressive_pressure=False)
    assert "Runtime: agent=quentin-executor" in ctx["skill_prompt"]
    assert "Tools (short summaries):" not in ctx["skill_prompt"]

