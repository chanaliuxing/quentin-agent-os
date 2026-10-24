from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from quentin.tools.manager import ToolPolicy


@dataclass(frozen=True)
class ToolPoliciesPack:
    id: str = "tool_policies"
    priority: int = 50

    def enabled(self, *, container: Any) -> bool:
        return True

    def register(self, *, tool_manager: Any, repo_root: Any, container: Any) -> None:
        tool_manager.set_safety_kernel(getattr(container, "safety_kernel", None))
        tool_manager.set_global_policy(ToolPolicy(deny=["system.*", "exec.*"]))
        tool_manager.set_environment_policy("staging", ToolPolicy(deny=["shell.*"]))
        tool_manager.set_environment_policy("prod", ToolPolicy(deny=["shell.*"]))

