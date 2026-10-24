from __future__ import annotations

from types import SimpleNamespace

import pytest

from quentin.multi_agent.coordinator import MultiAgentCoordinator
from quentin.multi_agent.roles import BaseAgentRole
from quentin.multi_agent.schemas import AgentRole, RoleVote


class _StubRole(BaseAgentRole):
    def __init__(self) -> None:
        super().__init__(AgentRole.SPEED, weight=1.0)

    def vote(self, model_stats, candidates, task_meta, settings):  # type: ignore[no-untyped-def]
        _ = (model_stats, task_meta, settings)
        return [RoleVote(role=self.role, model_name=candidates[0], score=1.0, reason="stub")]


class _StubRouter:
    async def get_stats(self, limit: int = 1000):  # type: ignore[no-untyped-def]
        _ = limit
        return {"models": []}


class _StubTracer:
    def span(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        return None


@pytest.mark.asyncio
async def test_choose_model_sets_prompt_mode_minimal_for_subagent() -> None:
    coord = MultiAgentCoordinator(
        tracer=_StubTracer(),  # type: ignore[arg-type]
        model_router=_StubRouter(),  # type: ignore[arg-type]
        settings=SimpleNamespace(),
        roles=[_StubRole()],
    )
    decision = await coord.choose_model(
        candidates=["m1", "m2"],
        task_meta={"domain": "core", "is_subagent": True},
    )
    assert decision.meta.get("prompt_mode") == "minimal"


@pytest.mark.asyncio
async def test_choose_model_sets_prompt_mode_full_for_parent() -> None:
    coord = MultiAgentCoordinator(
        tracer=_StubTracer(),  # type: ignore[arg-type]
        model_router=_StubRouter(),  # type: ignore[arg-type]
        settings=SimpleNamespace(),
        roles=[_StubRole()],
    )
    decision = await coord.choose_model(
        candidates=["m1", "m2"],
        task_meta={"domain": "core", "is_subagent": False},
    )
    assert decision.meta.get("prompt_mode") == "full"

