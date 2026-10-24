from __future__ import annotations

from pathlib import Path
import json


def test_spec_v3_sections_min_coverage() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    spec_path = repo_root / "blueprint" / "spec_v3_sections.json"
    assert spec_path.exists(), f"missing spec: {spec_path}"

    raw = json.loads(spec_path.read_text(encoding="utf-8") or "{}")
    assert raw.get("version") == "v3"

    items = raw.get("items") or []
    assert isinstance(items, list)
    assert len(items) >= 40, f"spec_v3_sections.json must not shrink below 40 items (got {len(items)})"

    ids: list[str] = []
    for it in items:
        assert isinstance(it, dict)
        item_id = str(it.get("id") or "").strip()
        assert item_id, "item missing id"
        ids.append(item_id)

        hints = it.get("hints") or {}
        assert isinstance(hints, dict)

        modules = hints.get("modules") or []
        assert isinstance(modules, list) and modules, f"{item_id}: hints.modules missing/empty"
        assert any((repo_root / str(p)).exists() for p in modules), f"{item_id}: no module path exists"

        cap_id = str(hints.get("trace_capability_id") or "").strip()
        assert cap_id, f"{item_id}: hints.trace_capability_id missing"

        signals = hints.get("trace_signals") or []
        assert isinstance(signals, list) and signals, f"{item_id}: hints.trace_signals missing/empty"
        assert any(str(s.get("trace_id") or "") == cap_id for s in signals if isinstance(s, dict)), (
            f"{item_id}: at least one trace_signals[].trace_id must equal trace_capability_id"
        )

    assert len(set(ids)) == len(ids), "duplicate ids found in spec_v3_sections.json"
