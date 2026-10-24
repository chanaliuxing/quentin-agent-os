from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from quentin.cognitive.loop_impl import CognitiveLoop, CognitiveTask


def _make_loop() -> CognitiveLoop:
    loop = CognitiveLoop.__new__(CognitiveLoop)
    loop.repo_root = Path(".").resolve()
    return loop


def test_build_planner_question_prompt_uses_legacy_when_flag_off(monkeypatch) -> None:
    monkeypatch.delenv("QUENTIN_FF_PROMPT_MIGRATION_M1_SYSTEM_FACTORY", raising=False)
    loop = _make_loop()
    goal = SimpleNamespace(goal_id="g1", metadata={})
    out = loop._build_planner_question_prompt(
        goal=goal,
        task_text="Fix parser",
        plan_schema_text='{"steps":[...]}',
        skill_suggestions=[],
        context={},
    )
    assert out.startswith("Decompose the given GOAL")
    assert "[SYSTEM]" not in out


def test_build_planner_question_prompt_uses_factory_when_flag_on(monkeypatch) -> None:
    monkeypatch.setenv("QUENTIN_FF_PROMPT_MIGRATION_M1_SYSTEM_FACTORY", "1")
    loop = _make_loop()
    goal = SimpleNamespace(goal_id="g1", metadata={"budget_remaining": "80%"})
    out = loop._build_planner_question_prompt(
        goal=goal,
        task_text="Fix parser",
        plan_schema_text='{"steps":[...]}',
        skill_suggestions=[{"skill_id": "skill.parse", "description": "parse input"}],
        context={"historical_attempts": "past fail"},
    )
    assert "[SYSTEM]" in out
    assert "[USER]" in out
    assert "You are a planning agent in Quentin cognitive loop." in out
    assert "Runtime: agent=quentin-cognitive-loop" in out


def test_build_executor_prompt_context_uses_factory_when_flag_on(monkeypatch) -> None:
    monkeypatch.setenv("QUENTIN_FF_PROMPT_MIGRATION_M1_SYSTEM_FACTORY", "1")
    loop = _make_loop()
    task = CognitiveTask(input_text="Do work", metadata={})
    goal = SimpleNamespace(goal_id="g2", metadata={"soul_prompt": "be concise"})
    ctx = loop._build_executor_prompt_context(task=task, goal=goal, progressive_pressure=True)
    assert "be concise" in ctx["soul_prompt"]
    assert "You are an execution agent in Quentin cognitive loop." in ctx["skill_prompt"]
    assert "Runtime: agent=quentin-executor" in ctx["skill_prompt"]
    assert (ctx.get("phase_payload") or {}).get("phase") == "executing"
