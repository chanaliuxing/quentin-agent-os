from __future__ import annotations

from pathlib import Path

from quentin.traces.paths import resolve_events_path, resolve_traces_dir


def test_resolve_traces_dir_default(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("QUENTIN_TRACES_DIR", raising=False)
    assert resolve_traces_dir(repo_root=tmp_path) == (tmp_path / "data" / "traces").resolve()


def test_resolve_traces_dir_override_absolute(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("QUENTIN_TRACES_DIR", str(tmp_path / "t"))
    assert resolve_traces_dir(repo_root=tmp_path) == (tmp_path / "t").resolve()


def test_resolve_traces_dir_override_relative(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("QUENTIN_TRACES_DIR", "rel_traces")
    assert resolve_traces_dir(repo_root=tmp_path) == (tmp_path / "rel_traces").resolve()


def test_resolve_events_path_uses_override(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("QUENTIN_TRACES_DIR", str(tmp_path / "mytraces"))
    assert resolve_events_path(repo_root=tmp_path) == (tmp_path / "mytraces" / "events.jsonl").resolve()

