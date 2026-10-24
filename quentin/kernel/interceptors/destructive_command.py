from __future__ import annotations

import re
from typing import Any, Dict, Optional, Tuple
from quentin.kernel.policy import ActionRequest
from quentin.kernel.interceptors.base import SecurityInterceptor

class DestructiveCommandInterceptor(SecurityInterceptor):
    """
    Detects and blocks inherently destructive or extremely risky shell commands.
    """
    def __init__(self, priority: int = 90):
        self._priority = priority
        self._blacklist = [
            r"rm\s+-rf\s+/",
            r"rm\s+-rf\s+\*",
            r"mkfs",
            r"dd\s+if=",
            r"shutdown",
            r"reboot",
            r"chmod\s+-R\s+777\s+/",
            r"DROP\s+DATABASE", # SQL injection in shell
        ]

    @property
    def id(self) -> str:
        return "destructive_command"

    @property
    def priority(self) -> int:
        return self._priority

    def intercept(self, action: ActionRequest) -> Tuple[bool, Optional[str], Dict[str, Any]]:
        # Only check shell actions
        if action.action_type not in ("shell", "exec", "command"):
            return True, None, {}

        cmd = str(action.metadata.get("command") or action.description or "").strip()
        if not cmd:
            return True, None, {}

        for pattern in self._blacklist:
            if re.search(pattern, cmd, re.IGNORECASE):
                return False, f"Potentially destructive command detected: {pattern}", {"detected_pattern": pattern}

        return True, None, {"status": "ok"}
