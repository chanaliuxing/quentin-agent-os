from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from quentin.tools.shell import shell_run_command


@dataclass(frozen=True)
class AliasesToolPack:
    id: str = "aliases"
    priority: int = 70

    def enabled(self, *, container: Any) -> bool:
        return True

    def register(self, *, tool_manager: Any, repo_root: Any, container: Any) -> None:
        tool_manager.register("memory-recall", shell_run_command)

