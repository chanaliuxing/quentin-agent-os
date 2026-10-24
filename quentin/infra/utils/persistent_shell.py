from __future__ import annotations

import subprocess
import os
import logging
from pathlib import Path
from typing import Dict, Any, Tuple, List

logger = logging.getLogger(__name__)

class StatefulShell:
    """
    Stateful Shell Session.
    Ensures 'cd' and 'export' persist between steps.
    Aligned with OpenClaw's node-shell logic.
    """
    def __init__(self, cwd: str = "."):
        self.cwd = Path(cwd).resolve()
        self.env = os.environ.copy()

    def _split_commands(self, command: str) -> List[str]:
        text = str(command or "").strip()
        if not text:
            return []
        # Best-effort splitter: keep behavior predictable for common sequences.
        parts: List[str] = []
        buf = ""
        in_single = False
        in_double = False
        for ch in text:
            if ch == "'" and not in_double:
                in_single = not in_single
            elif ch == '"' and not in_single:
                in_double = not in_double
            if ch == ";" and not in_single and not in_double:
                if buf.strip():
                    parts.append(buf.strip())
                buf = ""
                continue
            buf += ch
        if buf.strip():
            parts.append(buf.strip())
        return parts

    def _apply_builtin(self, cmd: str) -> Tuple[bool, str, int]:
        text = str(cmd or "").strip()
        if not text:
            return True, "", 0
        if text == "pwd":
            return True, str(self.cwd) + "\n", 0
        if text.startswith("cd "):
            target = text[3:].strip().strip('"').strip("'")
            if not target:
                target = str(Path.home())
            next_cwd = (self.cwd / target).resolve() if not os.path.isabs(target) else Path(target).resolve()
            if not next_cwd.exists() or not next_cwd.is_dir():
                return True, f"cd: no such file or directory: {target}\n", 1
            self.cwd = next_cwd
            return True, "", 0
        if text == "cd":
            self.cwd = Path.home().resolve()
            return True, "", 0
        if text.startswith("export "):
            body = text[len("export ") :].strip()
            if "=" not in body:
                return True, f"export: invalid assignment: {body}\n", 1
            key, val = body.split("=", 1)
            key = key.strip()
            val = val.strip().strip('"').strip("'")
            if not key:
                return True, f"export: invalid key: {body}\n", 1
            self.env[key] = val
            return True, "", 0
        if text.startswith("unset "):
            key = text[len("unset ") :].strip()
            if key:
                self.env.pop(key, None)
            return True, "", 0
        return False, "", 0

    def run(self, command: str) -> Tuple[str, int]:
        """
        Executes a command and updates the state (CWD and ENV).
        """
        chunks = self._split_commands(command)
        if not chunks:
            return "", 0
        out = ""
        last_code = 0
        try:
            for chunk in chunks:
                handled, builtin_out, builtin_code = self._apply_builtin(chunk)
                if handled:
                    out += builtin_out
                    last_code = int(builtin_code)
                    if last_code != 0:
                        break
                    continue
                proc = subprocess.run(
                    chunk,
                    shell=True,
                    executable="/bin/bash",
                    cwd=str(self.cwd),
                    env=self.env,
                    capture_output=True,
                    text=True,
                )
                out += (proc.stdout or "") + (proc.stderr or "")
                last_code = int(proc.returncode or 0)
                if last_code != 0:
                    break
            return out, last_code
        except Exception as e:
            return str(e), 1

# Global manager for session-based shells
shell_sessions: Dict[str, StatefulShell] = {}
