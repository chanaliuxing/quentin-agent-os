from __future__ import annotations

from fastapi.testclient import TestClient

from meta_agent.api.server import app
from quentin.runtime.system_events import SystemEventQueue


def test_background_task_events_endpoint(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    queue = SystemEventQueue(repo_root=tmp_path)
    queue.enqueue_event(
        session_id="api",
        event_type="background_task_completed",
        payload={"task_id": "task-1", "status": "completed", "result": "ok"},
        source="test",
    )
    client = TestClient(app)
    res = client.get("/system-events", params={"session_id": "api", "limit": 5, "drain": True})
    assert res.status_code == 200
    body = res.json()
    assert body["count"] == 1
    item = body["events"][0]
    assert item["status"] == "completed"
    assert item["task_id"] == "task-1"
