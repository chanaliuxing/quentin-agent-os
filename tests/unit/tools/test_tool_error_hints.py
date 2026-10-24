from __future__ import annotations

from pathlib import Path

import pytest

from quentin.tools.filesystem import fs_search_replace, fs_write_file
from quentin.tools.shell import shell_run_command


def test_fs_search_replace_not_found_has_hint(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    p = tmp_path / "mutable"
    p.mkdir(parents=True, exist_ok=True)
    target = p / "a.txt"
    target.write_text("hello world", encoding="utf-8")

    res = fs_search_replace({"path": "mutable/a.txt", "old_string": "absent", "new_string": "x"})
    assert res["status"] == "error"
    assert "hint" in res
    assert "next_actions" in res
    assert "not found" in str(res["error"]).lower()


def test_fs_search_replace_multiple_occurrences_has_hint(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    p = tmp_path / "mutable"
    p.mkdir(parents=True, exist_ok=True)
    target = p / "a.txt"
    target.write_text("hello world hello world", encoding="utf-8")

    res = fs_search_replace({"path": "mutable/a.txt", "old_string": "hello", "new_string": "x"})
    assert res["status"] == "error"
    assert "hint" in res
    assert "next_actions" in res
    assert "multiple occurrences" in str(res["error"]).lower()


def test_fs_write_path_denied_has_hint(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "quentin" / "kernel").mkdir(parents=True, exist_ok=True)
    res = fs_write_file({"path": "quentin/kernel/safety.py", "content": "x=1\n"})
    assert res["status"] == "error"
    assert "hint" in res
    assert "next_actions" in res
    assert "allowed roots" in str(res["error"]).lower()


def test_path_denied_has_allowed_roots_hint(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "quentin" / "kernel").mkdir(parents=True, exist_ok=True)
    res = fs_write_file({"path": "quentin/kernel/safety.py", "content": "x=1\n"})
    assert res["status"] == "error"
    assert "hint" in res
    assert "next_actions" in res
    assert "allowed roots" in str(res["error"]).lower()


def test_shell_timeout_has_hint(monkeypatch: pytest.MonkeyPatch) -> None:
    class _Proc:
        pid = 999

        def poll(self):  # type: ignore[no-untyped-def]
            return None

        def communicate(self):  # type: ignore[no-untyped-def]
            return ("", "")

    calls = {"n": 0}
    def _fake_time() -> float:
        calls["n"] += 1
        return 0.0 if calls["n"] == 1 else 200.0

    monkeypatch.setattr("quentin.tools.shell.subprocess.Popen", lambda *a, **k: _Proc())
    monkeypatch.setattr("quentin.tools.shell.time.time", _fake_time)
    monkeypatch.setattr("quentin.tools.shell.time.sleep", lambda _: None)
    monkeypatch.setattr("quentin.tools.shell._kill_process_group", lambda pid: None)

    res = shell_run_command({"command": "echo hi"})
    assert res["status"] == "error"
    assert "timed out" in str(res["error"]).lower()
    assert "hint" in res
    assert "next_actions" in res
    assert res.get("timeout_seconds") == 120
