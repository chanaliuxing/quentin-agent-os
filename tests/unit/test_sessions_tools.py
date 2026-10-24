from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from quentin.tools.execution_parity import (
    sessions_history_tool,
    sessions_list_tool,
    sessions_send_tool,
    sessions_spawn_tool,
)


def _ctx(tmp_path: Path):
    return SimpleNamespace(metadata={"repo_root": str(tmp_path.resolve()), "session_id": "main"})


def test_sessions_send_system_event_and_history(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)

    out = sessions_send_tool({"session_id": "s1", "text": "hello", "mode": "system_event"}, ctx)
    assert out["status"] == "ok"
    assert out["mode"] == "system_event"

    hist = sessions_history_tool({"session_id": "s1", "limit": 10}, ctx)
    assert hist["status"] == "ok"
    peek = list(hist.get("system_events_peek") or [])
    assert peek, "expected at least one system_event to be visible via peek"
    assert any(isinstance(ev, dict) and (ev.get("text") == "hello") for ev in peek)


def test_sessions_spawn_enqueues_task_and_list_sees_session(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    sp = sessions_spawn_tool({"text": "do thing", "domain": "core", "environment": "sandbox"}, ctx)
    assert sp["status"] == "ok"
    sid = str(sp.get("session_id") or "")
    assert sid.startswith("isolated:")

    out = sessions_list_tool({"limit": 200}, ctx)
    assert out["status"] == "ok"
    sessions = list(out.get("sessions") or [])
    assert any(isinstance(s, dict) and s.get("session_id") == sid for s in sessions)

