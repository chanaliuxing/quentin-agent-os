from __future__ import annotations

import json
from pathlib import Path

from quentin.blueprint.tracker import BlueprintGapTracker


def test_blueprint_tracker_honors_traces_dir_override(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("QUENTIN_TRACES_DIR", str(tmp_path / "traces"))

    # Spec expects traces for capability id "cap.x".
    spec = {
        "version": "v3.1",
        "items": [
            {
                "id": "x",
                "name": "x",
                "layer": "L1",
                "phase": "P0",
                "category": "test",
                "description": "x",
                "hints": {
                    "modules": [],
                    "trace_capability_id": "cap.x",
                },
            }
        ],
    }
    spec_path = tmp_path / "blueprint" / "spec.json"
    spec_path.parent.mkdir(parents=True, exist_ok=True)
    spec_path.write_text(json.dumps(spec), encoding="utf-8")

    # Write trace event into overridden traces dir.
    traces_dir = tmp_path / "traces"
    traces_dir.mkdir(parents=True, exist_ok=True)
    (traces_dir / "events.jsonl").write_text(
        json.dumps({"event_type": "decision", "trace_id": "cap.x", "payload": {"action": "anything"}}) + "\n",
        encoding="utf-8",
    )

    tracker = BlueprintGapTracker(repo_root=tmp_path, spec_path=spec_path)
    report = tracker.scan()
    assert report.total_items == 1
    assert report.items[0].has_traces is True

