# meta_agent/memory/types.py
from __future__ import annotations
from quentin.utils.time import now_iso, now_utc
from dataclasses import dataclass
from enum import Enum
from typing import Dict, Any, Optional
import datetime as dt
import uuid


class MemoryTier(str, Enum):
    STS = "sts"   # Short-Term Storage：最近对话 / trace 片段
    MTS = "mts"   # Mid-Term Storage：最近一段时间的模式、stage 经验
    LTS = "lts"   # Long-Term Storage：稳定的规则、原则、长期经验


@dataclass
class MemoryRecord:
    id: str
    tier: MemoryTier
    created_at: str
    updated_at: str

    kind: str
    text: str
    metadata: Dict[str, Any]

    importance: float
    recency_score: float
    usage_count: int

    last_accessed_at: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "tier": self.tier.value,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "kind": self.kind,
            "text": self.text,
            "metadata": self.metadata,
            "importance": self.importance,
            "recency_score": self.recency_score,
            "usage_count": self.usage_count,
            "last_accessed_at": self.last_accessed_at,
        }

    @staticmethod
    def new(
        text: str,
        tier: MemoryTier,
        kind: str = "observation",
        metadata: Optional[Dict[str, Any]] = None,
        importance: float = 0.5,
    ) -> "MemoryRecord":
        now = now_iso()
        return MemoryRecord(
            id=str(uuid.uuid4()),
            tier=tier,
            created_at=now,
            updated_at=now,
            kind=kind,
            text=text,
            metadata=metadata or {},
            importance=float(importance),
            recency_score=1.0,
            usage_count=0,
            last_accessed_at=None,
        )
