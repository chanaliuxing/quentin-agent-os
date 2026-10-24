from __future__ import annotations

from types import SimpleNamespace

import pytest

from quentin.multi_agent.coordinator import MultiAgentCoordinator
from quentin.multi_agent.roles import BaseAgentRole
from quentin.multi_agent.schemas import AgentRole, RoleVote
from quentin.runtime.system_events import SystemEventQueue


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
async def test_multi_agent_coordinator_emits_system_event_when_enabled(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("QUENTIN_MULTI_AGENT_EVENTS", "1")

    coord = MultiAgentCoordinator(
        tracer=_StubTracer(),  # type: ignore[arg-type]
        model_router=_StubRouter(),  # type: ignore[arg-type]
        settings=SimpleNamespace(),
        roles=[_StubRole()],
    )
    await coord.choose_model(
        candidates=["m1", "m2"],
        task_meta={"domain": "core", "repo_root": str(tmp_path), "session_id": "ma-session"},
    )

    queue = SystemEventQueue(repo_root=tmp_path)
    events = queue.list_events(session_id="ma-session", limit=10)
    assert any(e.event_type == "multi_agent_routing_decision" for e in events)

