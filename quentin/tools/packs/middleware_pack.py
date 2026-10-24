from __future__ import annotations

from dataclasses import dataclass
from typing import Any
import os


@dataclass(frozen=True)
class ToolMiddlewarePack:
    id: str = "tool_middleware"
    priority: int = 60

    def enabled(self, *, container: Any) -> bool:
        return True

    def register(self, *, tool_manager: Any, repo_root: Any, container: Any) -> None:
        raw = (os.getenv("QUENTIN_TOOL_MIDDLEWARE_PIPELINE", "0") or "").strip().lower()
        use_pipeline = raw in ("1", "true", "yes", "on")
        if use_pipeline and hasattr(tool_manager, "add_middleware"):
            from quentin.tools.middleware.path_fixer import PathFixerMiddleware
            from quentin.tools.middleware.error_hints import ErrorHintsMiddleware

            tool_manager.add_middleware(PathFixerMiddleware(repo_root=repo_root))
            tool_manager.add_middleware(ErrorHintsMiddleware())
            return

        from quentin.tools.middleware.path_fixer import get_path_correction_hook

        tool_manager.add_before_hook(get_path_correction_hook(repo_root=repo_root))
