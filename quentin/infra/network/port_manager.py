from __future__ import annotations

import socket
import subprocess
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class PortOwner:
    port: int
    pid: Optional[int] = None
    process: str = ""
    raw: str = ""


def is_port_available(*, host: str = "127.0.0.1", port: int) -> bool:
    """
    True if we can bind to host:port (best-effort).
    """
    p = int(port)
    if p <= 0 or p > 65535:
        return False
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind((host, p))
        return True
    except OSError:
        return False
    finally:
        try:
            s.close()
        except Exception:
            pass


def find_available_port(*, host: str = "127.0.0.1", start: int = 8000, end: int = 9000) -> int:
    """
    Find a free port in [start, end]. Raises RuntimeError if none found.
    """
    s = int(start)
    e = int(end)
    if s <= 0 or e <= 0 or e < s:
        raise ValueError("invalid port range")
    for p in range(s, e + 1):
        if is_port_available(host=host, port=p):
            return p
    raise RuntimeError(f"no free port found in range {s}-{e}")


def try_describe_port_owner(port: int) -> Optional[PortOwner]:
    """
    Best-effort: uses `lsof` when available (macOS/Linux).
    Returns None when not supported.
    """
    p = int(port)
    try:
        res = subprocess.run(
            ["lsof", "-nP", f"-iTCP:{p}", "-sTCP:LISTEN"],
            capture_output=True,
            text=True,
            check=False,
        )
    except Exception:
        return None

    out = (res.stdout or "").strip()
    if not out:
        return None
    lines = out.splitlines()
    if len(lines) < 2:
        return PortOwner(port=p, raw=out)
    # Typical lsof: COMMAND PID USER FD TYPE DEVICE SIZE/OFF NODE NAME
    parts = (lines[1] or "").split()
    if len(parts) >= 2:
        cmd = parts[0]
        try:
            pid = int(parts[1])
        except Exception:
            pid = None
        return PortOwner(port=p, pid=pid, process=cmd, raw=lines[1])
    return PortOwner(port=p, raw=lines[1])


__all__ = [
    "PortOwner",
    "is_port_available",
    "find_available_port",
    "try_describe_port_owner",
]

