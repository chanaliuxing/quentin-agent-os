from __future__ import annotations
import os

from typing import Any, List, Literal, Optional

from pydantic import BaseModel, Field, root_validator


class MemberConfig(BaseModel):
    member_id: str
    role: str
    model: str = Field(default_factory=lambda: os.environ["LLM_MODEL"])
    temperature: float = 0.2


class CouncilConfig(BaseModel):
    max_rounds: int = 3
    stall_rounds: int = 2
    summary_max_chars: int = 2400
    issue_similarity_threshold: float = 0.75
    members: List[MemberConfig] = Field(
        default_factory=lambda: [
            MemberConfig(member_id="planner", role="Planner"),
            MemberConfig(member_id="critic", role="Critic"),
            MemberConfig(member_id="judge", role="Judge"),
        ]
    )


class NextQuestion(BaseModel):
    target: str = "all"  # "all" or member_id
    question: str


class MemberReply(BaseModel):
    member_id: str
    stance: Literal["approve", "reject", "revise", "neutral"]
    key_points: List[str] = Field(default_factory=list)
    risks: List[str] = Field(default_factory=list)
    missing_info: List[str] = Field(default_factory=list)
    proposed_changes: List[str] = Field(default_factory=list)
    confidence: float = Field(0.6, ge=0.0, le=1.0)
    raw: str


class ModeratorOutput(BaseModel):
    verdict: Literal["approve", "reject", "revise", "debate"]
    debate_type: Optional[Literal["conflict", "needs_info", "quality_gap"]] = None
    open_issues: List[str] = Field(default_factory=list)
    next_round_plan: List[NextQuestion] = Field(default_factory=list)
    current_summary: str
    progress_notes: List[str] = Field(default_factory=list)
    resolved_issues: List[str] = Field(default_factory=list)
    newly_added_issues: List[str] = Field(default_factory=list)
    confidence: float = Field(0.6, ge=0.0, le=1.0)
    final_answer: Optional[Any] = None

    @root_validator(pre=True)
    def enforce_constraints(cls, values: dict) -> dict:
        verdict = values.get("verdict")
        if verdict != "debate" and values.get("final_answer") is None:
            values["final_answer"] = values.get("current_summary") or "missing_final_answer"
        if verdict == "debate" and not values.get("next_round_plan"):
            values["next_round_plan"] = [NextQuestion(target="all", question="Clarify key open issues")].copy()
        return values


class CouncilRound(BaseModel):
    round_id: int
    replies: List[MemberReply]
    moderator: ModeratorOutput
    working_memory: str


class CouncilOutcome(BaseModel):
    question: str
    final_output: ModeratorOutput
    rounds: List[CouncilRound]
    working_memory: str
    stalled: bool = False
    forced: bool = False
