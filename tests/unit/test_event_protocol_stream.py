from __future__ import annotations

from quentin.runtime.event_protocol import EventProtocol
from quentin.runtime.stream_protocol import StreamChunker
from quentin.runtime.system_events import SystemEventQueue


def test_event_protocol_emits_replayable_message_stream(tmp_path) -> None:
    queue = SystemEventQueue(repo_root=tmp_path)
    stream = StreamChunker(max_chunk_chars=5).process("<final>hello world</final>")

    EventProtocol(queue=queue, source="test").emit_message_stream(
        session_id="s1",
        turn_id="t1",
        stream=stream,
        meta={"x": 1},
    )

    events = queue.drain_brain_events(session_id="s1", limit=50)
    deltas = [e for e in events if e.event_type == "message.delta"]
    finals = [e for e in events if e.event_type == "message.final"]
    assert deltas
    assert finals

    replay = "".join(str((e.payload or {}).get("chunk") or "") for e in deltas).strip()
    assert replay == "hello world"
    assert str((finals[-1].payload or {}).get("text") or "") == "hello world"
