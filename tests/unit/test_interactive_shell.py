from __future__ import annotations

import time

from quentin.tools.interactive_shell import interactive_shell_tool


def test_interactive_shell_disabled_by_default(monkeypatch) -> None:
    monkeypatch.delenv("QUENTIN_INTERACTIVE_SHELL_ENABLED", raising=False)
    res = interactive_shell_tool({"action": "start", "command": "cat"})
    assert res["status"] == "error"
    assert "disabled" in (res.get("error") or "").lower()


def test_interactive_shell_start_write_poll_and_kill(monkeypatch) -> None:
    monkeypatch.setenv("QUENTIN_INTERACTIVE_SHELL_ENABLED", "true")
    monkeypatch.setenv("QUENTIN_INTERACTIVE_SHELL_WHITELIST", "cat")
    res = interactive_shell_tool({"action": "start", "command": "cat"})
    assert res["status"] == "ok"
    session_id = res.get("session_id")
    assert session_id

    res = interactive_shell_tool({"action": "write", "session_id": session_id, "input": "hello"})
    assert res["status"] == "ok"

    # give the PTY a moment
    time.sleep(0.05)
    res = interactive_shell_tool({"action": "poll", "session_id": session_id, "max_bytes": 1024})
    assert res["status"] == "ok"
    assert "hello" in (res.get("output") or "")

    res = interactive_shell_tool({"action": "kill", "session_id": session_id})
    assert res["status"] == "ok"


def test_interactive_shell_signal_forwarding(monkeypatch) -> None:
    monkeypatch.setenv("QUENTIN_INTERACTIVE_SHELL_ENABLED", "true")
    monkeypatch.setenv("QUENTIN_INTERACTIVE_SHELL_WHITELIST", "cat")
    res = interactive_shell_tool({"action": "start", "command": "cat"})
    assert res["status"] == "ok"
    session_id = res.get("session_id")
    assert session_id

    sig = interactive_shell_tool({"action": "signal", "session_id": session_id, "signal": "SIGINT"})
    assert sig["status"] == "ok"
    assert int(sig.get("signal_num") or 0) > 0

    res = interactive_shell_tool({"action": "kill", "session_id": session_id})
    assert res["status"] == "ok"
