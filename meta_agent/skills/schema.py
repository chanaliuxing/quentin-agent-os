# meta_agent/skills/schema.py
from __future__ import annotations
from quentin.utils.time import now_iso, now_utc
from dataclasses import dataclass, field, asdict
from typing import Dict, Any, List, Optional
import datetime as dt
import uuid


class SkillStatus:
    CANDIDATE = "candidate"
    ACTIVE = "active"
    DEPRECATED = "deprecated"


class SkillImplType:
    LLM_PROMPT = "llm_prompt"
    PYTHON_CODE = "python_code"
    WORKFLOW_REF = "workflow_ref"


@dataclass
class SkillStats:
    used_count: int = 0
    success_count: int = 0
    last_used_at: Optional[str] = None


@dataclass
class SkillDefinition:
    skill_id: str
    name: str
    domain: str
    tags: List[str]
    description: str
    signature: Dict[str, Any]
    impl_type: str
    impl_payload: Dict[str, Any]
    status: str
    stats: SkillStats
    created_at: str
    updated_at: str
    origin: str = "unknown"
    source_memory_ids: List[str] = field(default_factory=list)
    source_trace_ids: List[str] = field(default_factory=list)

    @classmethod
    def new(
        cls,
        *,
        name: str,
        domain: str,
        tags: List[str],
        description: str,
        signature: Dict[str, Any],
        impl_type: str,
        impl_payload: Dict[str, Any],
        status: str = SkillStatus.CANDIDATE,
    ) -> "SkillDefinition":
        now = now_iso()
        return cls(
            skill_id=str(uuid.uuid4()),
            name=name,
            domain=domain,
            tags=tags,
            description=description,
            signature=signature,
            impl_type=impl_type,
            impl_payload=impl_payload,
            status=status,
            stats=SkillStats(),
            created_at=now,
            updated_at=now,
            origin="skill_evolution_v1",
            source_memory_ids=[],
            source_trace_ids=[],
        )

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["stats"] = asdict(self.stats)
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SkillDefinition":
        stats = data.get("stats") or {}
        origin = data.get("origin") or "unknown"
        if not isinstance(origin, str):
            origin = "unknown"
        source_memory_ids = data.get("source_memory_ids") or []
        if not isinstance(source_memory_ids, list):
            source_memory_ids = []
        source_trace_ids = data.get("source_trace_ids") or []
        if not isinstance(source_trace_ids, list):
            source_trace_ids = []
        return cls(
            stats=SkillStats(**stats),
            origin=origin,
            source_memory_ids=[str(x) for x in source_memory_ids],
            source_trace_ids=[str(x) for x in source_trace_ids],
            **{k: v for k, v in data.items() if k != "stats"},
        )
