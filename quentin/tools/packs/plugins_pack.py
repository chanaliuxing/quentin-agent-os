from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from quentin.tools.plugin_loader import register_tool_plugins


@dataclass(frozen=True)
class PluginsToolPack:
    id: str = "plugins"
    priority: int = 40

    def enabled(self, *, container: Any) -> bool:
        return True

    def register(self, *, tool_manager: Any, repo_root: Any, container: Any) -> None:
        try:
            register_tool_plugins(tool_manager=tool_manager, repo_root=repo_root)
        except Exception:
            pass

