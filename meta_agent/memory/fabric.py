# meta_agent/memory/fabric.py
from __future__ import annotations
from quentin.utils.time import now_iso, now_utc
from typing import List, Optional
import datetime as dt

from meta_agent.memory.types import MemoryRecord, MemoryTier
from meta_agent.memory.store_sqlite import SqliteMemoryStore


class MemoryFabric:
    """
    高层接口：
    - write_observation / write_semantic / search
    - promote / decay
    - SleepLoop 会调用 consolidate() 做 nightly 迁移
    """

    def __init__(
        self,
        store: Optional[SqliteMemoryStore] = None,
        sts_max_age_hours: int = 24,
        mts_max_age_days: int = 14,
        promotion_importance_threshold: float = 0.7,
        promotion_usage_threshold: int = 3,
    ) -> None:
        self.store = store or SqliteMemoryStore()
        self.sts_max_age_hours = sts_max_age_hours
        self.mts_max_age_days = mts_max_age_days
        self.promotion_importance_threshold = promotion_importance_threshold
        self.promotion_usage_threshold = promotion_usage_threshold

    def write_observation(self, text: str, metadata: dict | None = None) -> MemoryRecord:
        rec = MemoryRecord.new(
            text=text,
            tier=MemoryTier.STS,
            kind="observation",
            metadata=metadata,
            importance=metadata.get("importance", 0.5) if metadata else 0.5,
        )
        self.store.upsert(rec)
        return rec

    def write_semantic(self, text: str, metadata: dict | None = None, tier: MemoryTier = MemoryTier.MTS) -> MemoryRecord:
        rec = MemoryRecord.new(
            text=text,
            tier=tier,
            kind="semantic",
            metadata=metadata,
            importance=metadata.get("importance", 0.7) if metadata else 0.7,
        )
        self.store.upsert(rec)
        return rec

    def search(
        self,
        query: str,
        tiers: Optional[List[MemoryTier]] = None,
        kind: Optional[str] = None,
        limit: int = 20,
    ) -> List[MemoryRecord]:
        recs = self.store.search(query=query, tiers=tiers, kind=kind, limit=limit)
        for r in recs:
            self.store.touch(r.id)
        return recs

    def consolidate(self) -> dict:
        now = now_utc()
        summary = {"promoted_sts_to_mts": 0, "demoted_mts": 0, "touched": 0}

        sts_recs = self.store.list_by_tier(MemoryTier.STS, limit=5000)
        promote_ids: List[str] = []
        for r in sts_recs:
            created = dt.datetime.fromisoformat(r.created_at.replace("Z", "+00:00"))
            age_hours = (now - created).total_seconds() / 3600.0
            if age_hours < self.sts_max_age_hours: continue

            if r.importance >= self.promotion_importance_threshold or r.usage_count >= self.promotion_usage_threshold:
                promote_ids.append(r.id)
        
        if promote_ids:
            self.store.bulk_update_tier(promote_ids, MemoryTier.MTS)
            summary["promoted_sts_to_mts"] = len(promote_ids)

        mts_recs = self.store.list_by_tier(MemoryTier.MTS, limit=5000)
        for r in mts_recs:
            created = dt.datetime.fromisoformat(r.created_at.replace("Z", "+00:00"))
            age_days = (now - created).days
            if age_days < self.mts_max_age_days: continue
            if r.importance < 0.4 and r.usage_count < 2:
                r.recency_score = max(0.0, r.recency_score - 0.2)
                r.updated_at = now.isoformat()
                self.store.upsert(r)
                summary["touched"] += 1

        return summary
