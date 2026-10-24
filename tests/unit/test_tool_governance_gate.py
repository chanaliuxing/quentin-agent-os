from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from quentin.governance.tool_council import ToolCandidate, ToolGovernanceGate


@dataclass
class _Decision:
    final: dict[str, Any]


class _StubCouncilManager:
    def __init__(self, answer: Any = None, *, raises: bool = False) -> None:
        self.answer = answer
        self.raises = raises

    def run_council(self, council_name: str, question: Any) -> _Decision:
        _ = (council_name, question)
        if self.raises:
            raise RuntimeError("council down")
        return _Decision(final={"answer": self.answer})


def test_tool_governance_gate_parses_json_string_answer_with_risk_veto() -> None:
    answer = json.dumps(
        {
            "votes": [
                {"role": "risk", "verdict": "reject", "reasoning": "dangerous"},
                {"role": "capability", "verdict": "approve", "reasoning": "useful"},
            ]
        }
    )
    gate = ToolGovernanceGate(council_manager=_StubCouncilManager(answer=answer))
    decision = gate.decide(
        candidate=ToolCandidate(tool_id="mcp.demo.tool", description="demo"),
        context={"env": "sandbox"},
    )
    assert decision.verdict == "reject"
    assert decision.risk_veto is True


def test_tool_governance_gate_falls_back_to_sandbox_only_on_missing_votes() -> None:
    gate = ToolGovernanceGate(council_manager=_StubCouncilManager(answer={"not_votes": []}))
    decision = gate.decide(
        candidate=ToolCandidate(tool_id="mcp.demo.tool", description="demo"),
        context={"env": "sandbox"},
    )
    assert decision.verdict == "sandbox_only"
    assert decision.rationale == "no_votes_fallback"


def test_tool_governance_gate_falls_back_to_sandbox_only_on_council_failure() -> None:
    gate = ToolGovernanceGate(council_manager=_StubCouncilManager(raises=True))
    decision = gate.decide(
        candidate=ToolCandidate(tool_id="mcp.demo.tool", description="demo"),
        context={"env": "sandbox"},
    )
    assert decision.verdict == "sandbox_only"
    assert decision.rationale == "no_votes_fallback"
