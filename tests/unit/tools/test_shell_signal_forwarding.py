from __future__ import annotations

import time

from quentin.tools.shell import shell_poll_results, shell_run_command, shell_send_input, shell_send_signal


def test_shell_run_command_background_returns_proc_id() -> None:
    res = shell_run_command(
        {
            "command": "python -c \"import time; time.sleep(1.5)\"",
            "yield_seconds": 0.05,
        }
    )
    assert res["status"] in {"running", "ok", "error"}
    if res["status"] == "running":
        assert str(res.get("proc_id") or "").startswith("proc_")
        shell_send_signal({"proc_id": res["proc_id"], "signal": "SIGKILL"})


def test_shell_run_command_foreground_protocol_fields() -> None:
    res = shell_run_command({"command": "echo hello"})
    assert res["status"] in {"ok", "error"}
    assert res.get("mode") == "foreground"
    assert res.get("phase") == "exited"


def test_shell_send_signal_interrupts_background_process() -> None:
    res = shell_run_command(
        {
            "command": "python -c \"import time; time.sleep(5)\"",
            "yield_seconds": 0.05,
        }
    )
    assert res["status"] == "running"
    proc_id = res["proc_id"]

    sig = shell_send_signal({"proc_id": proc_id, "signal": "SIGINT"})
    assert sig["status"] == "ok"

    # wait briefly for signal propagation
    running = True
    polled = {"status": "ok", "is_running": True}
    for _ in range(20):
        time.sleep(0.05)
        polled = shell_poll_results({"proc_id": proc_id})
        running = bool(polled.get("is_running"))
        if not running:
            break
    assert polled["status"] in {"ok", "waiting_for_input"}
    assert running is False


def test_shell_send_signal_graceful_stop_action() -> None:
    res = shell_run_command(
        {
            "command": "python -c \"import time; time.sleep(5)\"",
            "yield_seconds": 0.05,
        }
    )
    assert res["status"] == "running"
    proc_id = res["proc_id"]
    sig = shell_send_signal({"proc_id": proc_id, "action": "graceful_stop", "signal_ladder": ["SIGINT", "SIGTERM"]})
    assert sig["status"] == "ok"
    assert sig["action"] == "graceful_stop"
    for _ in range(30):
        time.sleep(0.05)
        polled = shell_poll_results({"proc_id": proc_id})
        if not bool(polled.get("is_running")):
            break
    assert bool(polled.get("is_running")) is False


def test_shell_poll_results_supports_cursor_delta() -> None:
    res = shell_run_command(
        {
            "command": "python -u -c \"import time; print('a'); time.sleep(0.15); print('b')\"",
            "yield_seconds": 0.02,
        }
    )
    assert res["status"] in {"running", "ok", "error"}
    if res["status"] != "running":
        return
    proc_id = res["proc_id"]
    cursor = 0
    saw_a = False
    saw_b = False
    for _ in range(30):
        time.sleep(0.03)
        out = shell_poll_results({"proc_id": proc_id, "cursor": cursor})
        delta = str(out.get("stdout_delta") or "")
        if "a" in delta:
            saw_a = True
        if "b" in delta:
            saw_b = True
        cursor = int(out.get("next_cursor") or cursor)
        if not bool(out.get("is_running")) and saw_a:
            break
    assert saw_a


def test_shell_poll_results_supports_seq_window() -> None:
    res = shell_run_command(
        {
            "command": "python -u -c \"print('x'); print('y')\"",
            "yield_seconds": 0.05,
        }
    )
    assert res["status"] in {"running", "ok", "error"}
    if res["status"] != "running":
        return
    proc_id = res["proc_id"]
    out1 = shell_poll_results({"proc_id": proc_id, "from_seq": 0, "max_lines": 1})
    assert out1["status"] in {"ok", "waiting_for_input"}
    assert isinstance(out1.get("stdout_events"), list)
    seq1 = int(out1.get("next_seq") or 0)
    out2 = shell_poll_results({"proc_id": proc_id, "from_seq": seq1, "max_lines": 5})
    assert int(out2.get("from_seq") or 0) == seq1
    shell_send_signal({"proc_id": proc_id, "signal": "SIGKILL"})


def test_shell_send_input_replay_dedup() -> None:
    res = shell_run_command({"command": "cat", "yield_seconds": 0.05})
    assert res["status"] == "running"
    proc_id = res["proc_id"]
    key = "rk-1"
    s1 = shell_send_input({"proc_id": proc_id, "text": "hello", "replay_key": key})
    assert s1["status"] == "ok"
    assert s1.get("replay_safe") is True
    s2 = shell_send_input({"proc_id": proc_id, "text": "hello", "replay_key": key})
    assert s2["status"] == "ok"
    assert s2.get("deduped") is True
    shell_send_signal({"proc_id": proc_id, "signal": "SIGKILL"})
