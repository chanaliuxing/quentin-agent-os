from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
import uuid
from quentin.utils.time import now_utc


class MemoryTier(str, Enum):
    STS = "short_term"
    MTS = "mid_term"
    LTS = "long_term"

    @classmethod
    def from_str(cls, label: str) -> MemoryTier:
        if not label: return cls.STS
        l = label.strip().upper()
        if l in ("STS", "SHORT_TERM", "SHORT"): return cls.STS
        if l in ("MTS", "MID_TERM", "MID"): return cls.MTS
        if l in ("LTS", "LONG_TERM", "LONG"): return cls.LTS
        return cls.STS

@dataclass
class MemoryUpdatePolicy:
    """
    Blueprint v3 fixed schema for per-record update policies.

    Stored in DB (sqlite/postgres) in a JSON column or encoded into metadata depending on store.
    """

    promotion_rule: Optional[Dict[str, Any]] = None
    decay_rule: Optional[Dict[str, Any]] = None
    consolidation_batch: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "promotion_rule": self.promotion_rule,
            "decay_rule": self.decay_rule,
            "consolidation_batch": self.consolidation_batch,
        }


@dataclass
class MemoryRecord:
    id: str
    tier: MemoryTier
    content: str
    created_at: datetime = field(default_factory=now_utc)
    updated_at: datetime = field(default_factory=now_utc)
    source: str = "unknown"  # e.g. "cognitive_loop", "sleep_loop", "skill_evolution"
    domain: Optional[str] = None
    topic: Optional[str] = None
    importance: float = 0.0  # heuristic score
    last_accessed_at: Optional[datetime] = None
    access_count: int = 0
    tags: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    consolidated_from_ids: List[str] = field(default_factory=list)  # for summaries
    supersedes_ids: List[str] = field(default_factory=list)
    kind: str = "episodic"
    vector: Optional[List[float]] = None
    relations: Dict[str, float] = field(default_factory=dict)
    update_policy: Optional[MemoryUpdatePolicy] = None
    update_history: List[Dict[str, Any]] = field(default_factory=list)

    @staticmethod
    def new(
        tier: MemoryTier,
        content: str,
        source: str,
        domain: Optional[str] = None,
        topic: Optional[str] = None,
        importance: float = 0.0,
        tags: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        consolidated_from_ids: Optional[List[str]] = None,
        supersedes_ids: Optional[List[str]] = None,
        vector: Optional[List[float]] = None,
        kind: str = "episodic",
        relations: Optional[Dict[str, float]] = None,
        update_policy: Optional[MemoryUpdatePolicy] = None,
        update_history: Optional[List[Dict[str, Any]]] = None,
    ) -> "MemoryRecord":
        now = now_utc()
        return MemoryRecord(
            id=str(uuid.uuid4()),
            tier=tier,
            content=content,
            created_at=now,
            updated_at=now,
            source=source,
            domain=domain,
            topic=topic,
            importance=importance,
            last_accessed_at=None,
            access_count=0,
            tags=tags or [],
            metadata=metadata or {},
            consolidated_from_ids=consolidated_from_ids or [],
            supersedes_ids=supersedes_ids or [],
            kind=kind,
            vector=vector,
            relations=relations or {},
            update_policy=update_policy,
            update_history=update_history or [],
        )


@dataclass
class MemoryQuery:
    text: Optional[str] = None         # 关键词/问题
    tier: Optional[MemoryTier] = None  # 限定 tier
    top_k: int = 10
    mode: str = "auto"                 # auto | vector_only | text_only | hybrid
    alpha: float = 0.5                 # vector weight for hybrid
    k_text: Optional[int] = None
    k_vec: Optional[int] = None
    min_text_score: float = 0.0
    min_vec_score: float = 0.0
    text_mode: Optional[str] = None        # "like" | "fts"
    min_importance: float = 0.0
    since: Optional[datetime] = None   # 时间过滤
    tags_any: Optional[List[str]] = None
    vector: Optional[List[float]] = None
    kind: Optional[str] = None
    domain: Optional[str] = None
    include_cross_domain: bool = True
    debug: bool = False
