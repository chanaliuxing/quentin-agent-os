# quentin/council/schema.py
from __future__ import annotations

from typing import Any, Optional, Literal, List
from pydantic import BaseModel, Field, model_validator

Verdict = Literal["approve", "reject", "revise", "debate"]
DebateType = Optional[Literal["conflict", "needs_info", "quality_gap"]]

class NextQuestion(BaseModel):
    target: str  # "all" or member_id
    question: str

class MemberReply(BaseModel):
    member_id: str
    stance: Literal["approve", "reject", "revise", "neutral"] = "neutral"
    key_points: List[str] = Field(default_factory=list)
    risks: List[str] = Field(default_factory=list)
    missing_info: List[str] = Field(default_factory=list)
    proposed_changes: List[str] = Field(default_factory=list)
    confidence: float = Field(default=0.6, ge=0.0, le=1.0)
    raw: str = ""

class ModeratorOutput(BaseModel):
    verdict: Verdict
    reasoning: str = ""

    debate_type: DebateType = None
    open_issues: List[str] = Field(default_factory=list)
    next_round_plan: List[NextQuestion] = Field(default_factory=list)

    # Working memory
    current_summary: str

    # Progress signals for stall detection
    progress_notes: List[str] = Field(default_factory=list)
    resolved_issues: List[str] = Field(default_factory=list)
    newly_added_issues: List[str] = Field(default_factory=list)
    confidence: float = Field(default=0.6, ge=0.0, le=1.0)

    # Must exist if verdict != debate
    final_answer: Optional[Any] = None

    @model_validator(mode="after")
    def _validate_constraints(self):
        if self.verdict == "debate":
            # debate should propose next steps
            if not self.next_round_plan:
                # allow empty plan but caller will fallback; not fatal
                pass
        else:
            # non-debate must have final_answer
            if self.final_answer is None:
                raise ValueError("final_answer is required when verdict is not 'debate'")
        return self
