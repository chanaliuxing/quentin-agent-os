from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from quentin.config.dual_track import DualTrackConfig
from quentin.config.mcp_security import MCPSecurityConfig
from quentin.memory.kinds import KIND_CAPABILITY_ACQUISITION_REQUEST
from quentin.meta.capability_gap import CapabilityGap
from quentin.meta.dual_track_acquirer import DualTrackAcquirer
from quentin.meta.dual_track_router import DualTrackDecision


@dataclass
class _Rec:
    id: str
    kind: str
    metadata: Dict[str, Any]


class _FakeFabric:
    def __init__(self) -> None:
        self.writes: List[_Rec] = []

    def remember_atomic(self, *, metadata: Dict[str, Any], kind: str, **kwargs: Any) -> None:  # type: ignore[no-untyped-def]
        _ = kwargs
        self.writes.append(_Rec(id=str(metadata.get("request_id") or ""), kind=kind, metadata=dict(metadata)))


class _StubCouncilManager:
    def __init__(self, verdict: str) -> None:
        self.verdict = verdict

    def run_council(self, council_name: str, question: Any) -> Any:  # type: ignore[no-untyped-def]
        _ = (council_name, question)
        return type(
            "Decision",
            (),
            {"final": {"answer": {"votes": [{"role": "risk", "verdict": self.verdict, "reasoning": "x"}]}}},
        )()


def test_acquirer_disabled_by_default() -> None:
    fabric = _FakeFabric()
    acq = DualTrackAcquirer(
        repo_root=".",
        memory_fabric=fabric,
        dual_track_config=DualTrackConfig(enabled=False),
        mcp_security=MCPSecurityConfig(enabled=True, enable_tool_governance=True),
        council_manager=_StubCouncilManager(verdict="approve"),
    )
    gap = CapabilityGap.new(gap_type="tool_not_found", gap_text="missing", domain="core", environment="sandbox", tool_name="mcp.s.t")
    req = acq.maybe_enqueue(gap=gap, decision=DualTrackDecision(track="mcp", reason="x", meta={}), ctx={})
    assert req is None


def test_acquirer_enqueues_governed_mcp_request_when_enabled() -> None:
    fabric = _FakeFabric()
    acq = DualTrackAcquirer(
        repo_root=".",
        memory_fabric=fabric,
        dual_track_config=DualTrackConfig(enabled=True, require_tool_governance=True),
        mcp_security=MCPSecurityConfig(enabled=True, enable_tool_governance=True),
        council_manager=_StubCouncilManager(verdict="approve"),
    )
    gap = CapabilityGap.new(gap_type="tool_not_found", gap_text="missing", domain="core", environment="sandbox", tool_name="mcp.s.t")
    req = acq.maybe_enqueue(gap=gap, decision=DualTrackDecision(track="mcp", reason="x", meta={}), ctx={})
    assert req is not None
    acq.write_request(req)
    assert fabric.writes
    assert fabric.writes[0].kind == KIND_CAPABILITY_ACQUISITION_REQUEST


def test_acquirer_blocks_high_risk_domains() -> None:
    fabric = _FakeFabric()
    acq = DualTrackAcquirer(
        repo_root=".",
        memory_fabric=fabric,
        dual_track_config=DualTrackConfig(enabled=True, blocked_domains=["legal"]),
        mcp_security=MCPSecurityConfig(enabled=True, enable_tool_governance=False),
        council_manager=_StubCouncilManager(verdict="approve"),
    )
    gap = CapabilityGap.new(gap_type="tool_not_found", gap_text="missing", domain="legal", environment="sandbox", tool_name="mcp.s.t")
    req = acq.maybe_enqueue(gap=gap, decision=DualTrackDecision(track="mcp", reason="x", meta={}), ctx={})
    assert req is None


def test_acquirer_blocks_mcp_request_when_governance_rejects() -> None:
    fabric = _FakeFabric()
    acq = DualTrackAcquirer(
        repo_root=".",
        memory_fabric=fabric,
        dual_track_config=DualTrackConfig(enabled=True, require_tool_governance=True),
        mcp_security=MCPSecurityConfig(enabled=True, enable_tool_governance=True),
        council_manager=_StubCouncilManager(verdict="reject"),
    )
    gap = CapabilityGap.new(gap_type="tool_not_found", gap_text="missing", domain="core", environment="sandbox", tool_name="mcp.s.t")
    req = acq.maybe_enqueue(gap=gap, decision=DualTrackDecision(track="mcp", reason="x", meta={}), ctx={})
    assert req is None


def test_acquirer_accepts_tool_blocked_gap_for_mcp_track() -> None:
    fabric = _FakeFabric()
    acq = DualTrackAcquirer(
        repo_root=".",
        memory_fabric=fabric,
        dual_track_config=DualTrackConfig(enabled=True, require_tool_governance=False),
        mcp_security=MCPSecurityConfig(enabled=True, enable_tool_governance=False),
        council_manager=_StubCouncilManager(verdict="approve"),
    )
    gap = CapabilityGap.new(gap_type="tool_blocked", gap_text="blocked_by_policy", domain="core", environment="sandbox", tool_name="mcp.s.t")
    req = acq.maybe_enqueue(gap=gap, decision=DualTrackDecision(track="mcp", reason="blocked", meta={}), ctx={})
    assert req is not None
    assert req.track == "mcp"
    assert req.payload["gap"]["gap_type"] == "tool_blocked"


def test_acquirer_self_programming_request_marks_patch_governance_required() -> None:
    fabric = _FakeFabric()
    acq = DualTrackAcquirer(
        repo_root=".",
        memory_fabric=fabric,
        dual_track_config=DualTrackConfig(enabled=True, require_patch_governance=True),
        mcp_security=MCPSecurityConfig(enabled=True, enable_tool_governance=False),
        council_manager=_StubCouncilManager(verdict="approve"),
    )
    gap = CapabilityGap.new(gap_type="missing_capability", gap_text="need local parser", domain="core", environment="sandbox", tool_name=None)
    req = acq.maybe_enqueue(
        gap=gap,
        decision=DualTrackDecision(track="self_programming", reason="fallback", meta={}),
        ctx={},
    )
    assert req is not None
    assert req.track == "self_programming"
    assert req.payload["requires_patch_governance"] is True
