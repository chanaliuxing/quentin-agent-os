from pathlib import Path

from app.gitops.merge import auto_resolve_conflicts_in_repo, resolve_conflict_markers


def test_resolve_conflict_markers_ours():
    content = "a\n<<<<<<< HEAD\nours\n=======\ntheirs\n>>>>>>> branch\nb\n"
    resolved = resolve_conflict_markers(content, strategy="ours")
    assert resolved == "a\nours\nb\n"


def test_resolve_conflict_markers_theirs():
    content = "a\n<<<<<<< HEAD\nours\n=======\ntheirs\n>>>>>>> branch\nb\n"
    resolved = resolve_conflict_markers(content, strategy="theirs")
    assert resolved == "a\ntheirs\nb\n"


def test_auto_resolve_conflicts_in_repo(tmp_path: Path):
    file_path = tmp_path / "conflicted.txt"
    file_path.write_text(
        "line1\n<<<<<<< HEAD\nleft\n=======\nright\n>>>>>>> branch\nline2\n",
        encoding="utf-8",
    )
    resolved_files = auto_resolve_conflicts_in_repo(tmp_path, strategy="ours")
    assert str(file_path) in resolved_files
    assert file_path.read_text(encoding="utf-8") == "line1\nleft\nline2\n"
