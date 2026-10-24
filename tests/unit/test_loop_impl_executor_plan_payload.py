from __future__ import annotations

import json

import pytest

from quentin.cognitive.loop_impl import CognitiveLoop, CognitiveTask
from quentin.goals.schema import GoalSpec


@pytest.mark.asyncio
async def test_run_executor_accepts_planner_payload_without_tool_args() -> None:
    """
    Regression: planner emits steps with only (step_id/description/skill_id/notes).
    The executor adapter must not infer tool calls like fs.read_file without required args (path),
    which previously crashed with "Missing path".
    """

    captured = {}

    class _DummyExecutor:
        async def execute_plan(self, *, goal, plan, context):  # type: ignore[no-untyped-def]
            _ = (goal, context)
            captured["plan"] = plan
            return {
                "success": True,
                "steps": [
                    {
                        "step_id": "s1",
                        "description": "do thing",
                        "success": True,
                        "result": {"status": "ok", "result": "ok"},
                    }
                ],
            }

    loop = CognitiveLoop.__new__(CognitiveLoop)
    loop.executor = _DummyExecutor()
    loop._build_executor_prompt_context = lambda **_: {}  # type: ignore[assignment]

    task = CognitiveTask(input_text="x", domain="maintenance", environment="sandbox", metadata={})
    goal = GoalSpec(goal_id="g1", title="t", description="d", domain="maintenance", environment="sandbox")

    plan_payload = {
        "steps": [
            {"step_id": "s1", "description": "read something", "skill_id": "fs.read_file", "notes": "n"}
        ]
    }
    out = await loop._run_executor(task, goal, json.dumps(plan_payload, ensure_ascii=False))

    assert captured["plan"]["steps"][0]["skill_id"] == "fs.read_file"
    assert out["final_output"] == "ok"


@pytest.mark.asyncio
async def test_run_executor_falls_back_to_single_step_on_non_json_summary() -> None:
    captured = {}

    class _DummyExecutor:
        async def execute_plan(self, *, goal, plan, context):  # type: ignore[no-untyped-def]
            _ = (goal, context)
            captured["plan"] = plan
            return {
                "success": True,
                "steps": [
                    {
                        "step_id": "s1",
                        "description": "fallback",
                        "success": True,
                        "result": {"status": "ok", "result": "done"},
                    }
                ],
            }

    loop = CognitiveLoop.__new__(CognitiveLoop)
    loop.executor = _DummyExecutor()
    loop._build_executor_prompt_context = lambda **_: {}  # type: ignore[assignment]

    task = CognitiveTask(input_text="x", domain="maintenance", environment="sandbox", metadata={})
    goal = GoalSpec(goal_id="g1", title="t", description="d", domain="maintenance", environment="sandbox")

    out = await loop._run_executor(task, goal, "just do it")

    assert captured["plan"]["steps"][0]["description"] == "just do it"
    assert out["final_output"] == "done"

