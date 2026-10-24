from __future__ import annotations

import json

from click.testing import CliRunner

from quentin.cli.qctl import cli
from quentin.runtime.system_events import SystemEventQueue


def test_qctl_wake_enqueues_system_event(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "wake",
            "--session-id",
            "s1",
            "--text",
            "done now",
            "--event-type",
            "background_task_done",
            "--source",
            "pytest",
        ],
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output.strip())
    assert payload["ok"] is True
    assert payload["session_id"] == "s1"

    q = SystemEventQueue(repo_root=tmp_path)
    events = q.drain_events(session_id="s1", limit=10)
    assert len(events) == 1
    assert events[0].event_type == "background_task_done"
    assert events[0].payload.get("message") == "done now"
