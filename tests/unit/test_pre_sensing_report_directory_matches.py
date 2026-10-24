from __future__ import annotations

from pathlib import Path

from quentin.cognitive.loop_impl import CognitiveLoop, CognitiveTask


def test_pre_sensing_report_directory_includes_keyword_matches(tmp_path: Path) -> None:
    repo_root = tmp_path
    tools_dir = repo_root / "extensions" / "tools"
    tools_dir.mkdir(parents=True)

    # Create many tool dirs so naive "first N" listing might miss the target.
    for i in range(60):
        (tools_dir / f"tool_{i:02d}").mkdir()
    (tools_dir / "gemini_cli").mkdir()

    loop = CognitiveLoop(repo_root=repo_root)
    task = CognitiveTask(input_text="Implement plugin gemini_cli under extensions/tools")
    focus = loop._infer_pre_sensing_focus_paths(task)
    report = loop._generate_sensing_report(task, focus)

    ev = [e for e in report.get("evidence", []) if e.get("path") == "extensions/tools"]
    assert ev, "expected evidence for extensions/tools"
    item = ev[0]
    matches = item.get("contents_matches") or []
    assert any("gemini_cli" == x for x in matches if isinstance(x, str))
    expected = item.get("expected_children") or []
    assert any(p.get("name") == "gemini_cli" and p.get("exists") is True for p in expected if isinstance(p, dict))

