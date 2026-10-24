# quentin/skills/schema.py
from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional
from datetime import datetime
import uuid
from quentin.utils.time import now_utc


class SkillStatus(str, Enum):
    DRAFT = "draft"          # 刚生成的技能，还没经过完整实验
    ACTIVE = "active"        # 已通过评估，可以在 Planner 中使用
    DEPRECATED = "deprecated"


@dataclass
class SkillExample:
    input: Dict[str, Any]
    output: Dict[str, Any]
    notes: str = ""


@dataclass
class SkillSpec:
    id: str
    name: str
    domain: str = "general"
    short_description: str = ""
    detailed_description: str = ""
    created_at: datetime = field(default_factory=now_utc)
    updated_at: datetime = field(default_factory=now_utc)
    created_by: str = "system"
    version: str = "0.1.0"
    status: SkillStatus = SkillStatus.DRAFT
    tags: List[str] = field(default_factory=list)
    parameters: Dict[str, Any] = field(default_factory=dict)
    examples: List[SkillExample] = field(default_factory=list)
    impl_stub_path: Optional[str] = None
    source_trace_ids: List[str] = field(default_factory=list)
    notes: str = ""
    
    # P5: Structural Parity - Business fields required by backends
    implementation_module: Optional[str] = None
    implementation_symbol: Optional[str] = None
    is_implemented: bool = False
    is_active: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)

    @staticmethod
    def new_from_council_json(data: Dict[str, Any]) -> "SkillSpec":
        """
        Build a SkillSpec from council JSON payload.
        """
        now = now_utc()
        examples_raw = data.get("examples", [])
        examples = []
        for e in examples_raw:
            try:
                examples.append(SkillExample(**e))
            except TypeError:
                # fallback when keys differ
                examples.append(SkillExample(input=e.get("input", {}), output=e.get("output", {}), notes=e.get("notes", "")))

        return SkillSpec(
            id=data.get("id", str(uuid.uuid4())),
            name=data.get("name", "unnamed-skill"),
            domain=data.get("domain", "general"),
            short_description=data.get("short_description", data.get("name", "")),
            detailed_description=data.get("detailed_description", data.get("short_description", "")),
            created_at=now,
            updated_at=now,
            created_by=data.get("created_by", "skill_evolution_loop"),
            version=data.get("version", "0.1.0"),
            status=SkillStatus(data.get("status", SkillStatus.DRAFT.value)) if isinstance(data.get("status"), str) else SkillStatus.DRAFT,
            tags=data.get("tags", []),
            parameters=data.get("parameters", {}),
            examples=examples,
            impl_stub_path=data.get("impl_stub_path"),
            source_trace_ids=data.get("source_trace_ids", []),
            notes=data.get("notes", ""),
        )


@dataclass
class SkillTestCase:
    input: Dict[str, Any]
    expected_output: Dict[str, Any]
    description: str = ""


@dataclass
class SkillStats:
    success_rate: float = 0.0
    avg_latency_ms: float = 0.0
    total_calls: int = 0


@dataclass
class SkillDefinition:
    skill_id: str
    name: str
    version: int = 1
    description: str = ""
    domain: str = "general"
    entry_point: str = ""
    tags: List[str] = field(default_factory=list)
    created_at: str = ""
    created_by: str = "system"
    safety_level: str = "medium"
    status: str = "active"
    supersedes: Optional[str] = None
    superseded_by: Optional[str] = None
    test_cases: List[SkillTestCase] = field(default_factory=list)
    performance_stats: SkillStats = field(default_factory=SkillStats)
    meta: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "skill_id": self.skill_id,
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "domain": self.domain,
            "entry_point": self.entry_point,
            "tags": self.tags,
            "created_at": self.created_at,
            "created_by": self.created_by,
            "safety_level": self.safety_level,
            "status": self.status,
            "supersedes": self.supersedes,
            "superseded_by": self.superseded_by,
            "test_cases": [tc.__dict__ for tc in self.test_cases] if self.test_cases else [],
            "performance_stats": self.performance_stats.__dict__,
            "meta": self.meta,
        }


@dataclass
class SkillCandidate:
    candidate_id: str
    base_skill_id: Optional[str]
    proposed_skill: SkillDefinition
    origin: Dict[str, Any] = field(default_factory=dict)
    status: str = "pending_eval"
    created_at: str = ""
    created_by: str = "self_programming_engine"
    notes: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "base_skill_id": self.base_skill_id,
            "proposed_skill": self.proposed_skill.to_dict(),
            "origin": self.origin,
            "status": self.status,
            "created_at": self.created_at,
            "created_by": self.created_by,
            "notes": self.notes,
        }


@dataclass
class SkillSupersedesRecord:
    old_skill_id: str
    new_skill_id: str
    reason: str = ""
    created_at: str = ""
    created_by: str = "system"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "old_skill_id": self.old_skill_id,
            "new_skill_id": self.new_skill_id,
            "reason": self.reason,
            "created_at": self.created_at,
            "created_by": self.created_by,
        }
