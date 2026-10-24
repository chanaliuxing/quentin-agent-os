from __future__ import annotations

from pathlib import Path

import pytest

from quentin.tools.filesystem import fs_read_file, fs_search_replace, fs_write_file, fs_get_write_policy


def _read_err(res: dict) -> str:
    return str(res.get("error") or "")


def test_fs_write_rejects_escape_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "mutable").mkdir(parents=True, exist_ok=True)
    res = fs_write_file({"path": "../../etc/passwd", "content": "x"})
    assert res["status"] == "error"
    assert "outside repo_root" in _read_err(res)


def test_fs_write_rejects_absolute_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "mutable").mkdir(parents=True, exist_ok=True)
    abs_target = tmp_path / "mutable" / "abs.py"
    res = fs_write_file({"path": str(abs_target), "content": "x"})
    assert res["status"] == "error"
    assert "Absolute path not allowed" in _read_err(res)


def test_fs_write_allows_mutable(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "mutable").mkdir(parents=True, exist_ok=True)
    res = fs_write_file({"path": "mutable/ok.py", "content": "x=1\n"})
    assert res["status"] == "ok"
    assert (tmp_path / "mutable" / "ok.py").exists()


def test_fs_write_allows_generated(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "generated").mkdir(parents=True, exist_ok=True)
    res = fs_write_file({"path": "generated/qqq_strategy_final.md", "content": "# report\n"})
    assert res["status"] == "ok"
    assert (tmp_path / "generated" / "qqq_strategy_final.md").exists()


def test_fs_write_denies_protected_code(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "quentin" / "kernel").mkdir(parents=True, exist_ok=True)
    res = fs_write_file({"path": "quentin/kernel/safety.py", "content": "x=1\n"})
    assert res["status"] == "error"
    assert "not under allowed roots" in _read_err(res)


def test_fs_read_allows_any_repo_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    p = tmp_path / "quentin" / "kernel"
    p.mkdir(parents=True, exist_ok=True)
    target = p / "safety.py"
    target.write_text("hello", encoding="utf-8")
    res = fs_read_file({"path": "quentin/kernel/safety.py"})
    assert res["status"] == "ok"
    assert res["result"] == "hello"


def test_fs_search_replace_denies_protected_code(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    p = tmp_path / "quentin" / "kernel"
    p.mkdir(parents=True, exist_ok=True)
    target = p / "safety.py"
    target.write_text("old", encoding="utf-8")
    res = fs_search_replace({"path": "quentin/kernel/safety.py", "old_string": "old", "new_string": "new"})
    assert res["status"] == "error"
    assert "not under allowed roots" in _read_err(res)


def test_fs_get_write_policy_exposes_allowed_roots(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("QUENTIN_PATH_GUARD_EXTRA_ALLOWED_ROOTS", "quentin/execution,docs/runbooks")
    res = fs_get_write_policy({})
    assert res["status"] == "ok"
    roots = list(res.get("allowed_roots") or [])
    assert "mutable" in roots
    assert "quentin/execution" in roots
    assert "docs/runbooks" in roots
