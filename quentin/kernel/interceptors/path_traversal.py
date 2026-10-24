from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional, Tuple
from quentin.kernel.policy import ActionRequest
from quentin.kernel.interceptors.base import SecurityInterceptor

class PathTraversalInterceptor(SecurityInterceptor):
    """
    Prevents file operations outside the repository root or allowed paths.
    """
    def __init__(self, repo_root: str | Path = ".", allowed_prefixes: Optional[List[str]] = None, priority: int = 100):
        self.repo_root = Path(repo_root).resolve()
        self._allowed_prefixes = [Path(p).resolve() for p in (allowed_prefixes or [])]
        self._priority = priority

    @property
    def id(self) -> str:
        return "path_traversal"

    @property
    def priority(self) -> int:
        return self._priority

    def intercept(self, action: ActionRequest) -> Tuple[bool, Optional[str], Dict[str, Any]]:
        # Only check file-related or shell actions that specify a path
        target_path = action.metadata.get("path") or action.metadata.get("target_path")
        if not target_path:
            return True, None, {}

        try:
            p = Path(str(target_path))
            if not p.is_absolute():
                p = (self.repo_root / p).resolve()
            else:
                p = p.resolve()
            
            # Check repo root
            if str(p).startswith(str(self.repo_root)):
                return True, None, {"status": "ok"}

            # Check explicit allowed prefixes (no hardcoding)
            for prefix in self._allowed_prefixes:
                if str(p).startswith(str(prefix)):
                    return True, None, {"status": "prefix_allowed", "prefix": str(prefix)}
                    
            hint = (
                f"ACCESS DENIED: The path '{target_path}' is protected. "
                f"SYSTEM POLICY: You are only allowed to write to '{self.repo_root}/' or declared safe zones. "
                "ACTION: Please re-route your output to a 'mutable/' path or check your current working directory with 'pwd'."
            )
            return False, hint, {"path": str(p), "policy_hint": hint}
        except Exception as e:
            return False, f"Failed to resolve path: {e}", {"error": str(e)}

        return True, None, {"status": "ok"}
