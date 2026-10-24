from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, List

from quentin.cognitive.perception.schemas import SituationAssessment
from quentin.cognitive.perception.situation_skill_router import MemoryBackedSituationSkillRouter


@dataclass
class _Rec:
    metadata: dict[str, Any] = field(default_factory=dict)


class _MemoryFabricStub:
    def __init__(self, records: List[_Rec] | None = None, raise_error: bool = False) -> None:
        self.records = list(records or [])
        self.raise_error = bool(raise_error)
        self.calls: int = 0

    def recall(self, _query: Any) -> List[_Rec]:
        self.calls += 1
        if self.raise_error:
            raise RuntimeError("recall failed")
        return list(self.records)


def test_router_skips_low_confidence() -> None:
    mem = _MemoryFabricStub(records=[_Rec(metadata={"situation_id": "s1", "recommended_skills": ["skill.a"]})])
    router = MemoryBackedSituationSkillRouter(memory_fabric=mem, min_confidence=0.7)
    out = router.route(
        situation=SituationAssessment(situation_id="s1", confidence=0.69, features={}),
        ctx={"domain": "core"},
    )
    assert out is None
    assert mem.calls == 0


def test_router_blocks_high_risk_domains() -> None:
    mem = _MemoryFabricStub(records=[_Rec(metadata={"situation_id": "s1", "recommended_skills": ["skill.a"]})])
    router = MemoryBackedSituationSkillRouter(memory_fabric=mem, min_confidence=0.6)
    out = router.route(
        situation=SituationAssessment(situation_id="s1", confidence=0.9, features={}),
        ctx={"domain": "legal"},
    )
    assert out is None
    assert mem.calls == 0


def test_router_returns_first_recommended_skill_on_match() -> None:
    mem = _MemoryFabricStub(
        records=[
            _Rec(metadata={"situation_id": "other", "recommended_skills": ["skill.ignore"]}),
            _Rec(metadata={"situation_id": "s1", "recommended_skills": ["skill.hit", "skill.second"]}),
        ]
    )
    router = MemoryBackedSituationSkillRouter(memory_fabric=mem, min_confidence=0.6)
    out = router.route(
        situation=SituationAssessment(situation_id="s1", confidence=0.9, features={}),
        ctx={"domain": "core"},
    )
    assert out is not None
    assert out.skill_id == "skill.hit"
    assert out.reason == "situation_profile_recommended_skill"
    assert out.metadata.get("situation_id") == "s1"
    assert mem.calls == 1


def test_router_returns_none_when_recall_raises() -> None:
    mem = _MemoryFabricStub(raise_error=True)
    router = MemoryBackedSituationSkillRouter(memory_fabric=mem, min_confidence=0.6)
    out = router.route(
        situation=SituationAssessment(situation_id="s1", confidence=0.9, features={}),
        ctx={"domain": "core"},
    )
    assert out is None
    assert mem.calls == 1
