from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from quentin.tools.interactive_shell import interactive_shell_tool


@dataclass(frozen=True)
class InteractiveShellToolPack:
    id: str = "interactive_shell"
    priority: int = 80

    def enabled(self, *, container: Any) -> bool:
        # Keep behavior unchanged: tool may be registered even if runtime blocks it.
        return True

    def register(self, *, tool_manager: Any, repo_root: Any, container: Any) -> None:
        tool_manager.register("shell.interactive", interactive_shell_tool)
        tool_manager.register("shell_interactive", interactive_shell_tool)

