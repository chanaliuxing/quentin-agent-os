from __future__ import annotations

from quentin.config.mcp_security import MCPSecurityConfig
from quentin.meta.capability_gap import CapabilityGap
from quentin.meta.dual_track_router import RuleBasedDualTrackRouter


def test_dual_track_router_falls_back_when_mcp_disabled() -> None:
    router = RuleBasedDualTrackRouter(mcp_security=MCPSecurityConfig(enabled=False), repo_root=".")
    gap = CapabilityGap.new(gap_type="tool_not_found", gap_text="x", domain="core", environment="sandbox", tool_name="mcp.s.t")
    decision = router.route(gap=gap, ctx={})
    assert decision.track == "self_programming"


def test_dual_track_router_prefers_mcp_when_enabled() -> None:
    router = RuleBasedDualTrackRouter(mcp_security=MCPSecurityConfig(enabled=True), repo_root=".")
    gap = CapabilityGap.new(gap_type="tool_not_found", gap_text="x", domain="core", environment="sandbox", tool_name="mcp.s.t")
    decision = router.route(gap=gap, ctx={})
    assert decision.track == "mcp"

