from __future__ import annotations

import re
import shlex
from typing import Any, Dict, Optional, Tuple
from quentin.kernel.policy import ActionRequest
from quentin.kernel.interceptors.base import SecurityInterceptor

class BashInjectionInterceptor(SecurityInterceptor):
    """
    Hard Interceptor: Prevents complex shell chains and injection attempts.
    Targets commands that try to bypass single-command tools.
    """
    def __init__(self, priority: int = 150):
        self._priority = priority
        # Patterns that indicate command chaining or complex shell logic
        self._danger_tokens = [
            r";",          # Sequential commands
            r"&&",         # Conditional execution
            r"\|\|",       # Conditional execution
            r"\|",         # Pipes (only allow if tool specifically allows it)
            r"`",          # Backticks
            r"\$\(",       # Subshells
            r">",          # Redirection
            r">>",         # Append redirection
            r"&",          # Backgrounding
        ]

    @property
    def id(self) -> str:
        return "bash_injection"

    @property
    def priority(self) -> int:
        return self._priority

    def intercept(self, action: ActionRequest) -> Tuple[bool, Optional[str], Dict[str, Any]]:
        if action.action_type not in ("shell", "exec", "command"):
            return True, None, {}

        cmd = str(action.metadata.get("command") or action.description or "").strip()
        if not cmd:
            return True, None, {}

        # 1. Simple shell escaping check
        try:
            tokens = shlex.split(cmd)
        except ValueError as e:
            return False, f"Malformed shell command: {e}", {"error": "parse_error"}

        # 2. Check for danger tokens outside of quoted strings
        # We look for tokens that shlex doesn't consume as single arguments
        # (simplified: search raw string for common shell metacharacters)
        for token in self._danger_tokens:
            if re.search(token, cmd):
                # Exception: allow pipes for 'rg' or 'grep' if they are simple
                if token == r"\|" and any(x in cmd for x in ("grep", "rg", "count")):
                    continue
                return False, f"Shell metacharacter '{token}' is forbidden in this context.", {"token": token}

        return True, None, {"status": "ok", "tokens_count": len(tokens)}
