from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from quentin.tools.usage.tool_knowledge_sink import ToolKnowledgeUsageSink


@dataclass(frozen=True)
class UsageSinksToolPack:
    id: str = "usage_sinks"
    priority: int = 110

    def enabled(self, *, container: Any) -> bool:
        return True

    def register(self, *, tool_manager: Any, repo_root: Any, container: Any) -> None:
        try:
            tool_manager.add_usage_sink(ToolKnowledgeUsageSink(memory_fabric=container.memory_fabric))
        except Exception:
            pass

