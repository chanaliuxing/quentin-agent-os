from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional, Tuple
from quentin.kernel.policy import ActionRequest
from quentin.kernel.interceptors.base import SecurityInterceptor

class SensitiveFileAccessInterceptor(SecurityInterceptor):
    """
    Hard Interceptor: Blocks access to mission-critical files regardless of prompt instructions.
    """
    def __init__(self, repo_root: str | Path = ".", priority: int = 200):
        self.repo_root = Path(repo_root).resolve()
        self._priority = priority
        self._forbidden_patterns = [
            ".git/",
            "config/secrets",
            "data/audit",
            "data/auth_profiles.json", # P5: Protect credential refs
            "governance.yaml",
            ".env",
            "pyproject.toml", # Prevent self-modifying project config without research approval
            "/etc/",
            "/var/",
            "~/",
        ]

    @property
    def id(self) -> str:
        return "sensitive_files"

    @property
    def priority(self) -> int:
        return self._priority

    def intercept(self, action: ActionRequest) -> Tuple[bool, Optional[str], Dict[str, Any]]:
        target_path = str(action.metadata.get("path") or action.metadata.get("target_path") or "")
        if not target_path:
            # Also scan the description/command for path-like strings
            content = str(action.description or "") + " " + str(action.metadata.get("command") or "")
            for pattern in self._forbidden_patterns:
                if pattern in content:
                    return False, f"Action references sensitive path pattern: {pattern}", {"pattern": pattern}
            return True, None, {}

        for pattern in self._forbidden_patterns:
            if pattern in target_path:
                return False, f"Access to sensitive file/path is forbidden: {pattern}", {"path": target_path}

        return True, None, {"status": "ok"}
