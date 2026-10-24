import json
import os
from pathlib import Path


def test_jsonl_trace_recorder_appends_gz(tmp_path: Path, monkeypatch) -> None:
    # Isolate trace output under tmp to avoid polluting repo state.
    traces_dir = tmp_path / "traces"
    monkeypatch.setenv("QUENTIN_TRACES_DIR", str(traces_dir))

    from quentin.traces.core import JsonlTraceRecorder, TraceEvent

    rec = JsonlTraceRecorder(repo_root=str(tmp_path))
    ev = TraceEvent(event_id="e1", trace_id="t1", event_type="tool_call", payload={"k": "v"})
    rec.record_event(ev)

    gz_path = traces_dir / "events.jsonl.gz"
    assert gz_path.exists()

    import gzip

    lines = []
    with gzip.open(gz_path, "rt", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                lines.append(json.loads(line))
    assert any(obj.get("event_id") == "e1" for obj in lines)

