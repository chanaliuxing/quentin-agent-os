from __future__ import annotations

from pathlib import Path

from quentin.cognitive.loop import CognitiveLoop


def test_planner_receives_file_tree_snapshot_by_default(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    (repo / "quentin" / "tools").mkdir(parents=True, exist_ok=True)
    (repo / "quentin" / "tools" / "manager.py").write_text("x=1\n", encoding="utf-8")

    loop = CognitiveLoop.__new__(CognitiveLoop)
    loop.repo_root = repo  # type: ignore[attr-defined]
    snapshot = loop._get_environment_snapshot()  # type: ignore[attr-defined]
    assert "Project Root Structure" in snapshot
    assert "quentin/" in snapshot


def test_executor_avoids_nonexistent_path_by_triggering_lookup(tmp_path: Path) -> None:
    loop = CognitiveLoop.__new__(CognitiveLoop)
    loop.repo_root = tmp_path  # type: ignore[attr-defined]
    repaired, notes = loop._repair_plan_quality(  # type: ignore[attr-defined]
        task_text="fix missing file path hallucination",
        context={"candidate_files": []},
        steps=[{"step_id": "s1", "description": "write to foo/bar/baz.py using fs.write_file"}],
    )
    assert repaired
    first_desc = str(repaired[0].get("description") or "").lower()
    assert "discovery precheck" in first_desc or "inspect workspace" in first_desc
    assert any("inject_discovery_precheck" in n or "decompose_single_step_fallback" in n for n in notes)


def test_context_injection_respects_budget_limits(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    deep = repo / "quentin" / "module"
    deep.mkdir(parents=True, exist_ok=True)
    for i in range(250):
        (deep / f"f{i}.py").write_text("x=1\n", encoding="utf-8")

    loop = CognitiveLoop.__new__(CognitiveLoop)
    loop.repo_root = repo  # type: ignore[attr-defined]
    snapshot = loop._get_environment_snapshot()  # type: ignore[attr-defined]
    assert len(snapshot.splitlines()) <= 150
