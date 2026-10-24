from __future__ import annotations

import json
from pathlib import Path


def test_blueprint_spec_v3_1_json_is_loadable() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    path = repo_root / "blueprint" / "spec_v3_1.json"
    raw = json.loads(path.read_text(encoding="utf-8"))
    assert raw.get("version") == "v3.1"
    items = raw.get("items") or []
    assert isinstance(items, list) and items
    assert any(it.get("id") == "cognitive.perception.context-layer" for it in items if isinstance(it, dict))

