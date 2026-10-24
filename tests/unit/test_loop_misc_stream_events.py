from __future__ import annotations

from types import SimpleNamespace

from quentin.cognitive.loop_misc import sanitize_executor_output
from quentin.runtime.system_events import SystemEventQueue


class _FakeLoop:
    def __init__(self, queue: SystemEventQueue):
        self.system_event_queue = queue
        self.executor = None


def test_sanitize_executor_output_emits_message_events(tmp_path) -> None:
    queue = SystemEventQueue(repo_root=tmp_path)
    loop = _FakeLoop(queue)

    final_output, actions = sanitize_executor_output(
        loop=loop,
        exec_res={
            "final_output": "<think>secret</think><final>Hello world from stream</final>",
            "actions_summary": "done",
            "_session_id": "s1",
            "_turn_id": "t1",
        },
        logger=SimpleNamespace(info=lambda *a, **k: None, debug=lambda *a, **k: None),
    )

    assert final_output == "Hello world from stream"
    assert actions == "done"

    events = queue.drain_brain_events(session_id="s1", limit=50)
    types = [e.event_type for e in events]
    assert "message.delta" in types
    assert "message.final" in types
    last = [e for e in events if e.event_type == "message.final"][-1]
    assert str((last.payload or {}).get("text") or "") == "Hello world from stream"
    assert bool((last.payload or {}).get("has_hidden_thinking")) is True


def test_silent_reply_does_not_leak_to_visible_output(tmp_path) -> None:
    queue = SystemEventQueue(repo_root=tmp_path)
    loop = _FakeLoop(queue)

    final_output, _actions = sanitize_executor_output(
        loop=loop,
        exec_res={
            "final_output": "[[silent]] should not leak",
            "actions_summary": "done",
            "_session_id": "s2",
            "_turn_id": "t2",
        },
        logger=SimpleNamespace(info=lambda *a, **k: None, debug=lambda *a, **k: None),
    )

    assert final_output == ""
    events = queue.drain_brain_events(session_id="s2", limit=20)
    final_ev = [e for e in events if e.event_type == "message.final"][-1]
    assert bool((final_ev.payload or {}).get("silent")) is True
