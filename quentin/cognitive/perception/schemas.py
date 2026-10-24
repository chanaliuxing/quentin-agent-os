from __future__ import annotations

from dataclasses import dataclass, asdict, field
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class SituationAssessment:
    situation_id: str
    confidence: float
    features: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class AttentionPack:
    """
    Planner-facing reduced context bundle.

    - selected_context: the only context that should be directly injected into the planner prompt
    - reduction_ratio: (1 - len(selected)/len(original)) approx; 0 means no reduction
    - debug_refs: any optional pointers for replay/debug (kept out of planner by default)
    """

    selected_context: Dict[str, Any]
    reduction_ratio: float
    debug_refs: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ExpectedState:
    situation_id: str
    markers: List[str] = field(default_factory=list)
    template_id: Optional[str] = None
    fallback_skills: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class PredictionError:
    error_type: str
    severity: str = "low"  # low|medium|high
    missing_markers: List[str] = field(default_factory=list)
    observed_markers: List[str] = field(default_factory=list)
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SkillInvocation:
    skill_id: str
    reason: str
    min_confidence: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class PerceptionSnapshot:
    situation: SituationAssessment
    attention: Optional[AttentionPack] = None
    expected_state: Optional[ExpectedState] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "situation": self.situation.to_dict(),
            "attention": self.attention.to_dict() if self.attention else None,
            "expected_state": self.expected_state.to_dict() if self.expected_state else None,
            "metadata": dict(self.metadata or {})
        }

