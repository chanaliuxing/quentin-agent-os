from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from quentin.tools.providers.mcp import MCPToolProvider


@dataclass(frozen=True)
class MCPToolPack:
    id: str = "mcp"
    priority: int = 10

    def enabled(self, *, container: Any) -> bool:
        # Provider itself is gated by config/mcp_security.yaml; keep this pack always on.
        return True

    def register(self, *, tool_manager: Any, repo_root: Any, container: Any) -> None:
        try:
            from quentin.config.mcp_security import load_mcp_security
            from quentin.governance.tool_council import ToolGovernanceGate
            from quentin.council.manager import CouncilManager

            mcp_cfg = load_mcp_security(repo_root)
            gate = None
            if mcp_cfg.enabled and mcp_cfg.enable_tool_governance:
                gate = ToolGovernanceGate(
                    council_manager=CouncilManager(repo_root=repo_root, model_router=container.model_router)
                )
            MCPToolProvider(tool_governance_gate=gate).register(tool_manager=tool_manager, repo_root=str(repo_root))
        except Exception:
            pass
