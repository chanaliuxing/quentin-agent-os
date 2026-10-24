from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional
from quentin.tools.middleware.base import ToolMiddleware, BeforeOutcome, AfterOutcome, ToolCallContextLike
from quentin.tools.schemas import ToolCallResult
from quentin.kernel.path_guard import PathGuard

logger = logging.getLogger(__name__)

class SecurityAuditMiddleware:
    """
    P5: Ported from OpenClaw's sanitizer.ts and exec-safety.ts.
    Pre-flight parameter auditing to block path traversal and illegal operations.
    """
    id = "security_auditor"
    priority = 110 # Very high priority, must run before execution

    def __init__(self, repo_root: str | Path):
        self.repo_root = Path(repo_root).resolve()
        self.path_guard = PathGuard(self.repo_root)

    def before(self, *, tool_name: str, params: Dict[str, Any], ctx: ToolCallContextLike) -> BeforeOutcome:
        # 1. Path Traversal Audit
        path_keys = ["path", "file", "target_path", "dir", "directory", "file_path"]
        for key in path_keys:
            if key in params and isinstance(params[key], str):
                p = params[key]
                try:
                    self.path_guard.ensure_allowed_path(p)
                except PermissionError as e:
                    logger.error(f"SecurityAudit: Blocked tool {tool_name} due to path violation: {p}")
                    return BeforeOutcome(params=params, blocked=True, reason=f"Path violation: {str(e)}")

        # 2. Command Injection Audit (Simple heuristic)
        if tool_name.startswith("shell."):
            cmd = str(params.get("command", ""))
            # Block suspicious characters often used for injection if not properly quoted
            # This is a basic layer; OpenClaw uses more sophisticated parsing.
            forbidden = ["; rm ", "| rm ", "& rm ", "> /dev/sda"]
            for f in forbidden:
                if f in cmd:
                    return BeforeOutcome(params=params, blocked=True, reason=f"Suspicious shell command pattern blocked: {f}")

        return BeforeOutcome(params=params)

    def after(self, *, tool_name: str, params: Dict[str, Any], result: ToolCallResult, ctx: ToolCallContextLike) -> AfterOutcome:
        return AfterOutcome(result=result)
