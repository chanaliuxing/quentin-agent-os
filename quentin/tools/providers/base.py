from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Protocol


@dataclass(frozen=True)
class ProviderReport:
    provider_id: str
    enabled: bool
    registered_tools: List[str]
    errors: List[Dict[str, Any]]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "provider_id": self.provider_id,
            "enabled": bool(self.enabled),
            "registered_tools": list(self.registered_tools),
            "errors": list(self.errors),
        }


class ToolProvider(Protocol):
    provider_id: str

    def register(self, *, tool_manager: Any, repo_root: str) -> ProviderReport: ...

