from __future__ import annotations

import os
import shlex
import subprocess
import uuid
import select
import signal
from dataclasses import dataclass
from typing import Any, Dict, Optional


def _env_bool(name: str, default: str = "0") -> bool:
    v = (os.getenv(name, default) or "").strip().lower()
    return v in ("1", "true", "yes", "on")


def _parse_whitelist() -> set[str]:
    raw = (os.getenv("QUENTIN_INTERACTIVE_SHELL_WHITELIST", "") or "").strip()
    if not raw:
        return set()
    return {x.strip() for x in raw.split(",") if x.strip()}


@dataclass
class _ShellSession:
    proc: subprocess.Popen
    buf: str = ""


_SESSIONS: Dict[str, _ShellSession] = {}

_SIGNAL_MAP = {
    "SIGINT": signal.SIGINT,
    "INT": signal.SIGINT,
    "CTRL_C": signal.SIGINT,
    "SIGTERM": signal.SIGTERM,
    "TERM": signal.SIGTERM,
    "SIGKILL": signal.SIGKILL,
    "KILL": signal.SIGKILL,
}


def _send_signal_to_session(proc: subprocess.Popen, sig: int) -> None:
    # Prefer process-group signaling so children (tail -f, piped commands) also get the signal.
    try:
        pgid = os.getpgid(proc.pid)
        os.killpg(pgid, sig)
        return
    except Exception:
        pass
    proc.send_signal(sig)


def interactive_shell_tool(params: Dict[str, Any], ctx: Any = None) -> Dict[str, Any]:
    """
    Minimal interactive shell with session lifecycle:
    - start: spawn command, returns session_id
    - write: write input to stdin
    - poll: read available stdout/stderr (non-blocking best-effort)
    - kill: terminate the process and drop session

    This handler returns plain dicts (ToolManager wraps into ToolCallResult when needed).
    """
    _ = ctx
    action = str((params or {}).get("action") or "").strip().lower() or "start"

    if not _env_bool("QUENTIN_INTERACTIVE_SHELL_ENABLED", "0"):
        return {"status": "error", "error": "interactive shell disabled"}

    if action == "start":
        command = str((params or {}).get("command") or "").strip()
        if not command:
            return {"status": "error", "error": "missing command"}

        try:
            toks = shlex.split(command)
        except Exception:
            toks = command.split()
        head = toks[0] if toks else ""

        whitelist = _parse_whitelist()
        if whitelist and head not in whitelist:
            return {"status": "error", "error": f"command not allowed: {head}"}

        try:
            proc = subprocess.Popen(
                command,
                shell=False,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=0,
                start_new_session=True,
            )
        except FileNotFoundError:
            # If command is not an executable (e.g. "cat -n"), fallback to shell parsing.
            proc = subprocess.Popen(
                command,
                shell=True,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=0,
                start_new_session=True,
            )

        # Make stdout non-blocking for poll().
        try:
            if proc.stdout is not None:
                os.set_blocking(proc.stdout.fileno(), False)
        except Exception:
            pass

        sid = uuid.uuid4().hex
        _SESSIONS[sid] = _ShellSession(proc=proc)
        return {"status": "ok", "session_id": sid}

    session_id = str((params or {}).get("session_id") or "").strip()
    if not session_id or session_id not in _SESSIONS:
        return {"status": "error", "error": "unknown session_id"}

    sess = _SESSIONS[session_id]
    proc = sess.proc

    if action == "write":
        data = str((params or {}).get("input") or "")
        if proc.stdin is None:
            return {"status": "error", "error": "stdin closed"}
        try:
            # Ensure line-terminated input for common TTY-like programs.
            if data and not data.endswith("\n"):
                data += "\n"
            proc.stdin.write(data)
            proc.stdin.flush()
            return {"status": "ok"}
        except Exception as e:
            return {"status": "error", "error": f"write failed: {e}"}

    if action == "poll":
        max_bytes = int((params or {}).get("max_bytes") or 4096)
        out = ""
        try:
            if proc.stdout is not None:
                fd = proc.stdout.fileno()
                r, _, _ = select.select([fd], [], [], 0.0)
                if r:
                    raw = os.read(fd, max_bytes)
                    if raw:
                        out = raw.decode(errors="ignore")
        except Exception:
            out = ""
        if out:
            sess.buf += out
        return {"status": "ok", "output": out, "exit_code": proc.poll()}

    if action == "kill":
        try:
            _send_signal_to_session(proc, signal.SIGTERM)
        except Exception:
            pass
        try:
            _send_signal_to_session(proc, signal.SIGKILL)
        except Exception:
            pass
        _SESSIONS.pop(session_id, None)
        return {"status": "ok"}

    if action == "signal":
        raw = str((params or {}).get("signal") or "SIGINT").strip().upper()
        sig_val = _SIGNAL_MAP.get(raw)
        if sig_val is None:
            try:
                sig_val = int(raw)
            except Exception:
                return {"status": "error", "error": f"unknown signal: {raw}"}
        try:
            _send_signal_to_session(proc, int(sig_val))
            return {"status": "ok", "signal": raw, "signal_num": int(sig_val)}
        except Exception as e:
            return {"status": "error", "error": f"signal failed: {e}"}

    return {"status": "error", "error": f"unknown action: {action}"}
