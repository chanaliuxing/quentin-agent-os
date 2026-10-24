from __future__ import annotations

import json
from pathlib import Path

from quentin.blueprint.tracker import BlueprintGapTracker


def test_tracker_marks_done_when_optional_evidence_not_required(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir(parents=True, exist_ok=True)
    (tmp_path / "src" / "mod.py").write_text("x = 1\n", encoding="utf-8")

    spec = {
        "version": "v3-test",
        "items": [
            {
                "id": "cap.optional.evidence",
                "name": "Optional evidence capability",
                "layer": "L1",
                "phase": "P1",
                "category": "test",
                "description": "No trace/experiment hints",
                "hints": {"modules": ["src/mod.py"]},
            }
        ],
    }
    spec_path = tmp_path / "blueprint" / "spec_v3.json"
    spec_path.parent.mkdir(parents=True, exist_ok=True)
    spec_path.write_text(json.dumps(spec), encoding="utf-8")

    report = BlueprintGapTracker(repo_root=tmp_path, spec_path=spec_path).scan()
    assert report.total_items == 1
    item = report.items[0]
    assert item.status == "done"
    assert item.expects_traces is False
    assert item.expects_experiments is False
    assert item.has_traces is True
    assert item.has_experiments is True
    assert abs(item.score - 1.0) < 1e-9


def test_tracker_marks_missing_when_module_absent(tmp_path: Path) -> None:
    spec = {
        "version": "v3-test",
        "items": [
            {
                "id": "cap.missing.file",
                "name": "Missing file capability",
                "layer": "L1",
                "phase": "P1",
                "category": "test",
                "description": "Module does not exist",
                "hints": {"modules": ["src/not_found.py"], "trace_capability_id": "cap.missing.file"},
            }
        ],
    }
    spec_path = tmp_path / "blueprint" / "spec_v3.json"
    spec_path.parent.mkdir(parents=True, exist_ok=True)
    spec_path.write_text(json.dumps(spec), encoding="utf-8")

    report = BlueprintGapTracker(repo_root=tmp_path, spec_path=spec_path).scan()
    assert report.total_items == 1
    item = report.items[0]
    assert item.status == "missing"
    assert item.file_implemented is False
