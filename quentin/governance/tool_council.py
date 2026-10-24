from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Dict, Iterable, List, Optional

from quentin.council.manager import CouncilDecision, CouncilManager, CouncilQuestion


@dataclass(frozen=True)
class ToolCandidate:
    """
    A candidate tool (typically MCP) that the system may register/enable.
    """

    tool_id: str  # e.g. "mcp.server.tool" or "server/tool"
    signature: Optional[str] = None
    description: str = ""
    categories: List[str] = None  # type: ignore[assignment]
    source: str = "unknown"
    meta: Dict[str, Any] = None  # type: ignore[assignment]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tool_id": self.tool_id,
            "signature": self.signature,
            "description": self.description,
            "categories": list(self.categories or []),
            "source": self.source,
            "meta": dict(self.meta or {}),
        }


@dataclass(frozen=True)
class ToolGovernanceVote:
    role: str  # "risk" | "capability" | "cost" | ...
    verdict: str  # "approve" | "sandbox_only" | "reject"
    reasoning: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ToolGovernanceDecision:
    verdict: str  # "approve" | "sandbox_only" | "reject"
    rationale: str
    risk_veto: bool = False
    votes: List[ToolGovernanceVote] = None  # type: ignore[assignment]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "verdict": self.verdict,
            "rationale": self.rationale,
            "risk_veto": bool(self.risk_veto),
            "votes": [v.to_dict() for v in (self.votes or [])],
        }


def aggregate_tool_votes(votes: Iterable[ToolGovernanceVote]) -> ToolGovernanceDecision:
    """
    Governance aggregation rules (v3.1):
    - Risk veto: any risk==reject -> reject
    - Otherwise majority of {approve, sandbox_only, reject}
    - Ties fall back to sandbox_only (conservative)
    """
    vs = [v for v in (votes or []) if isinstance(v, ToolGovernanceVote)]
    for v in vs:
        if str(v.role or "").strip().lower() in {"risk", "risk-agent", "risk_agent"} and str(v.verdict).lower() == "reject":
            return ToolGovernanceDecision(
                verdict="reject",
                rationale="risk_veto",
                risk_veto=True,
                votes=vs,
            )

    counts: Dict[str, int] = {"approve": 0, "sandbox_only": 0, "reject": 0}
    for v in vs:
        key = str(v.verdict or "").strip().lower()
        if key in counts:
            counts[key] += 1

    best = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    top_label, top_count = best[0]
    # Tie check
    tied = [k for k, c in counts.items() if c == top_count and c > 0]
    if len(tied) >= 2:
        verdict = "sandbox_only"
        rationale = "tie_fallback_sandbox_only"
    else:
        verdict = top_label if top_count > 0 else "sandbox_only"
        rationale = "majority"
    return ToolGovernanceDecision(verdict=verdict, rationale=rationale, risk_veto=False, votes=vs)


class ToolGovernanceGate:
    """
    Pluggable gate that can be called before registering/enabling tools.

    Default behavior is conservative if the council output is missing/unparseable.
    """

    def __init__(self, *, council_manager: Any, council_name: str = "tool_governance") -> None:
        self.council_manager = council_manager
        self.council_name = council_name

    def decide(self, *, candidate: ToolCandidate, context: Dict[str, Any]) -> ToolGovernanceDecision:
        prompt = (
            "You are a tool governance council.\n"
            "Decide whether to APPROVE, SANDBOX_ONLY, or REJECT the candidate tool.\n"
            "Rule: Risk veto applies (Risk-Agent=REJECT => overall REJECT).\n\n"
            "Return ONLY JSON:\n"
            "{\n"
            '  "votes": [\n'
            '    {"role":"risk","verdict":"approve|sandbox_only|reject","reasoning":"..."},\n'
            '    {"role":"capability","verdict":"approve|sandbox_only|reject","reasoning":"..."},\n'
            '    {"role":"cost","verdict":"approve|sandbox_only|reject","reasoning":"..."}\n'
            "  ]\n"
            "}\n"
        )
        question = CouncilQuestion(
            topic="tool_governance",
            importance="high",
            prompt=prompt,
            payload={"candidate": candidate.to_dict(), "context": dict(context or {})},
        )
        raw: Optional[CouncilDecision] = None
        try:
            raw = self.council_manager.run_council(self.council_name, question)
        except Exception:
            raw = None

        votes: List[ToolGovernanceVote] = []
        try:
            final = raw.final if raw is not None else {}
            ans = final.get("answer") if isinstance(final, dict) else None
            if isinstance(ans, str):
                import json

                ans = json.loads(ans)
            obj = ans if isinstance(ans, dict) else final
            items = obj.get("votes") if isinstance(obj, dict) else None
            if isinstance(items, list):
                for it in items:
                    if not isinstance(it, dict):
                        continue
                    votes.append(
                        ToolGovernanceVote(
                            role=str(it.get("role") or "").strip() or "unknown",
                            verdict=str(it.get("verdict") or "").strip().lower() or "sandbox_only",
                            reasoning=str(it.get("reasoning") or ""),
                        )
                    )
        except Exception:
            votes = []

        if not votes:
            return ToolGovernanceDecision(verdict="sandbox_only", rationale="no_votes_fallback", votes=[])
        return aggregate_tool_votes(votes)

