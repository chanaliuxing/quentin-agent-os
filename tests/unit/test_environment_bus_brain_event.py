from __future__ import annotations

import asyncio
from pathlib import Path

from quentin.infra.events.environment_bus import EnvironmentEventBus
from quentin.runtime.system_events import SystemEventQueue


def test_environment_bus_maps_to_brain_event(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    q = SystemEventQueue(repo_root=".")
    monkeypatch.setattr("quentin.runtime.system_events.system_events", q)
    bus = EnvironmentEventBus()
    bus._pending_payloads.clear()
    bus._debounce_tasks.clear()

    async def _run() -> None:
        bus.emit("ui_event", {"kind": "toast", "message": "ok"}, debounce_ms=10)
        await asyncio.sleep(0.05)

    asyncio.run(_run())
    events = q.list_brain_events(session_id="global", limit=20)
    mapped = [e for e in events if str(e.event_type or "") == "channel.ui_event"]
    assert mapped
    assert mapped[-1].category == "channel"
    assert mapped[-1].payload.get("event_type") == "ui_event"
