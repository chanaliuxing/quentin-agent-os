from __future__ import annotations

import pytest

from quentin.agents.coordinator import MultiAgentCoordinator
from quentin.agents.roles import AgentInput, AgentOutput
from quentin.models.router import ModelRouter


class _StubAgent:
    def __init__(self, role: str) -> None:
        self._role = role

    async def run(self, router: ModelRouter, inp: AgentInput) -> AgentOutput:
        return AgentOutput(role=self._role, model="stub", content=f"{self._role}:{inp.prompt}", meta={})


@pytest.mark.asyncio
async def test_multi_agent_coordinator_returns_views():
    router = ModelRouter()
    coord = MultiAgentCoordinator(router=router, roles={"a": _StubAgent("a"), "b": _StubAgent("b")})
    res = await coord.run_multi_view(
        AgentInput(role="test", task_type="chat", domain="core", prompt="hello", meta={})
    )

    assert res["final"] is not None
    assert len(res["views"]) == 2
