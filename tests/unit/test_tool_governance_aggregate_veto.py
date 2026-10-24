from __future__ import annotations

from quentin.governance.tool_council import ToolGovernanceVote, aggregate_tool_votes


def test_tool_governance_risk_veto_rejects() -> None:
    decision = aggregate_tool_votes(
        [
            ToolGovernanceVote(role="risk", verdict="reject", reasoning="danger"),
            ToolGovernanceVote(role="capability", verdict="approve", reasoning="useful"),
            ToolGovernanceVote(role="cost", verdict="approve", reasoning="cheap"),
        ]
    )
    assert decision.verdict == "reject"
    assert decision.risk_veto is True


def test_tool_governance_majority_approve() -> None:
    decision = aggregate_tool_votes(
        [
            ToolGovernanceVote(role="risk", verdict="approve", reasoning="ok"),
            ToolGovernanceVote(role="capability", verdict="approve", reasoning="useful"),
            ToolGovernanceVote(role="cost", verdict="sandbox_only", reasoning="unknown"),
        ]
    )
    assert decision.verdict == "approve"


def test_tool_governance_tie_falls_back_to_sandbox_only() -> None:
    decision = aggregate_tool_votes(
        [
            ToolGovernanceVote(role="risk", verdict="approve", reasoning="ok"),
            ToolGovernanceVote(role="capability", verdict="reject", reasoning="not needed"),
        ]
    )
    assert decision.verdict == "sandbox_only"

