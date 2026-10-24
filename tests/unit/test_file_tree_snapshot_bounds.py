from __future__ import annotations

from quentin.cognitive.context_snapshots.file_tree import FileTreeSnapshotProvider


def test_file_tree_snapshot_respects_depth_and_file_count(tmp_path, monkeypatch) -> None:
    (tmp_path / "a").mkdir()
    (tmp_path / "a" / "b").mkdir()
    (tmp_path / "a" / "b" / "c").mkdir()
    (tmp_path / "a" / "root.txt").write_text("x", encoding="utf-8")
    (tmp_path / "a" / "b" / "deep.txt").write_text("x", encoding="utf-8")
    (tmp_path / "a" / "b" / "c" / "too_deep.txt").write_text("x", encoding="utf-8")
    (tmp_path / ".hidden").mkdir()
    (tmp_path / ".hidden" / "ignored.txt").write_text("x", encoding="utf-8")

    monkeypatch.setenv("QUENTIN_SNAPSHOT_TREE_DEPTH", "2")
    monkeypatch.setenv("QUENTIN_SNAPSHOT_TREE_MAX_FILES", "2")

    block = FileTreeSnapshotProvider().collect(tmp_path, {})
    assert block is not None
    text = block.content
    assert "root.txt" in text
    assert ".hidden" not in text
    assert "too_deep.txt" not in text
    assert int((block.meta or {}).get("files_count", 0)) <= 2

