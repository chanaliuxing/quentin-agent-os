from __future__ import annotations

import json
from pathlib import Path

from quentin.blueprint.gaps import BlueprintGapTracker


def test_gaps_tracker_uses_canonical_status_with_legacy_alias(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir(parents=True, exist_ok=True)
    (tmp_path / "src" / "done.py").write_text("def done_symbol():\n    return True\n", encoding="utf-8")

    spec = {
        "version": "3.0",
        "requirements": [
            {
                "id": "cap.done",
                "category": "core",
                "description": "done capability",
                "priority": "high",
                "module_hint": "src/done.py",
                "symbols_expected": ["done_symbol"],
            },
            {
                "id": "cap.missing",
                "category": "core",
                "description": "missing capability",
                "priority": "high",
                "module_hint": "src/missing.py",
            },
        ],
    }
    caps = {"implemented_ids": ["cap.done"]}

    spec_path = tmp_path / "blueprint" / "meta_agent_v3_spec.json"
    spec_path.parent.mkdir(parents=True, exist_ok=True)
    spec_path.write_text(json.dumps(spec), encoding="utf-8")
    caps_path = tmp_path / "data" / "blueprint" / "capabilities.json"
    caps_path.parent.mkdir(parents=True, exist_ok=True)
    caps_path.write_text(json.dumps(caps), encoding="utf-8")

    tracker = BlueprintGapTracker(repo_root=tmp_path, spec_path=spec_path, capabilities_path=caps_path)
    results = tracker.scan_with_evidence()
    by_id = {r.requirement_id: r for r in results}

    assert by_id["cap.done"].meta["status"] == "done"
    assert by_id["cap.done"].meta["legacy_status"] == "implemented"
    assert by_id["cap.missing"].meta["status"] == "missing"
    assert by_id["cap.missing"].meta["legacy_status"] == "gap"

    gap_only = tracker.scan()
    assert {g.requirement_id for g in gap_only} == {"cap.missing"}
