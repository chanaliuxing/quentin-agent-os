from __future__ import annotations

import json

import pytest

from quentin.planning.planner import HierarchicalPlanner
from quentin.skills.registry import SkillRegistry


class _StubLLM:
    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def complete(self, prompt: str) -> str:
        # Deterministic JSON for tests; no network dependency.
        return json.dumps(self._payload)

    def extract_json(self, text: str) -> dict:
        return json.loads(text)


@pytest.mark.asyncio
async def test_hierarchical_planner_returns_steps_from_llm_json(tmp_path):
    llm = _StubLLM(
        {
            "steps": [
                {"description": "step one", "kind": "tool", "name": "read", "args": {"path": "README.md"}},
                {"description": "step two", "kind": "llm_call", "name": "summarize", "args": {"k": 3}},
            ]
        }
    )
    registry = SkillRegistry(path=tmp_path / "skills.json")
    planner = HierarchicalPlanner(llm=llm, skill_registry=registry, max_depth=1)

    plan = await planner.plan(
        goal="do a thing",
        context={"domain": "core", "environment": "sandbox"},
        success_criteria=["works"],
        hard_constraints=["no network"],
    )

    assert plan.goal == "do a thing"
    assert len(plan.steps) == 2
    assert plan.steps[0].kind == "tool"
    assert plan.steps[0].name == "read"

