from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from quentin.tools.execution_parity import memory_get_tool, memory_search_tool


def _ctx(tmp_path: Path):
    return SimpleNamespace(metadata={"repo_root": str(tmp_path.resolve())})


def test_memory_search_and_get_allowlisted(tmp_path: Path) -> None:
    (tmp_path / "MEMORY.md").write_text("Decision: use foo\nTODO: bar\n", encoding="utf-8")
    (tmp_path / "docs").mkdir(parents=True, exist_ok=True)
    (tmp_path / "docs" / "note.md").write_text("We discussed baz\n", encoding="utf-8")

    ctx = _ctx(tmp_path)
    out = memory_search_tool({"query": "TODO", "max_results": 5}, ctx)
    assert out["status"] == "ok"
    assert out["results"]
    hit = out["results"][0]
    assert "MEMORY.md" in str(hit.get("path") or "")

    got = memory_get_tool({"path": "MEMORY.md", "from": 1, "lines": 5}, ctx)
    assert got["status"] == "ok"
    assert "Decision" in got["text"]


def test_memory_get_blocks_non_allowlisted_path(tmp_path: Path) -> None:
    (tmp_path / "secrets.txt").write_text("nope", encoding="utf-8")
    ctx = _ctx(tmp_path)
    out = memory_get_tool({"path": "secrets.txt", "from": 1, "lines": 2}, ctx)
    assert out["status"] == "error"

