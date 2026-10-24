from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional, Protocol

from quentin.config.mcp_security import MCPSecurityConfig, load_mcp_security
from quentin.meta.capability_gap import CapabilityGap


@dataclass(frozen=True)
class DualTrackDecision:
    """
    Routing decision for a capability gap.
    """

    track: str  # "mcp" | "self_programming"
    reason: str
    meta: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return {"track": self.track, "reason": self.reason, "meta": dict(self.meta or {})}


class DualTrackRouter(Protocol):
    def route(self, *, gap: CapabilityGap, ctx: Dict[str, Any]) -> DualTrackDecision: ...


class RuleBasedDualTrackRouter:
    """
    v0 dual-track router:
    - If MCP runtime integration is enabled and the gap is a missing external tool -> choose MCP
    - Otherwise fall back to self-programming
    """

    def __init__(self, *, mcp_security: Optional[MCPSecurityConfig] = None, repo_root: str = ".") -> None:
        self.repo_root = repo_root
        self.mcp_security = mcp_security or load_mcp_security(repo_root)

    def route(self, *, gap: CapabilityGap, ctx: Dict[str, Any]) -> DualTrackDecision:
        _ = ctx
        gtype = str(gap.gap_type or "").strip().lower()
        tool = str(gap.tool_name or "").strip()

        # Prefer MCP for missing MCP tool names when MCP is enabled.
        if self.mcp_security.enabled:
            if tool.startswith("mcp.") or gtype == "tool_not_found":
                return DualTrackDecision(track="mcp", reason="mcp_enabled_tool_gap", meta={"tool_name": tool, "gap_type": gtype})

        return DualTrackDecision(track="self_programming", reason="fallback_self_programming", meta={"tool_name": tool, "gap_type": gtype})

