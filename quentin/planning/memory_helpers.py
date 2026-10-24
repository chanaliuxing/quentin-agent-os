from __future__ import annotations
from typing import List
from datetime import timedelta

from quentin.memory.fabric import MemoryFabric
from quentin.memory.models import MemoryQuery, MemoryTier, MemoryRecord
from quentin.utils.time import now_utc

_memory_fabric: MemoryFabric | None = None


def _get_memory_fabric() -> MemoryFabric:
    global _memory_fabric
    if _memory_fabric is None:
        _memory_fabric = MemoryFabric()
    return _memory_fabric


def recall_for_task(domain: str, task_description: str, top_k: int = 5) -> List[MemoryRecord]:
    """
    简单策略：
    - 只查 MTS/LTS（SleepLoop 整理后的稳定记忆）
    - 用 task_description 作为关键词
    - 限定最近 30 天（可调）
    """
    since = now_utc() - timedelta(days=30)

    # In the new MemoryFabric, query doesn't have a tier filter like this.
    # It queries all tiers by default if tier is None.
    # We can query MTS and LTS separately and combine.
    
    q_mts = MemoryQuery(
        text=task_description,
        tier=MemoryTier.MTS,
        top_k=top_k,
        min_importance=0.2,
        since=since,
        tags_any=[domain] if domain else None,
    )
    memory_fabric = _get_memory_fabric()
    mts_records = memory_fabric.recall(q_mts)

    q_lts = MemoryQuery(
        text=task_description,
        tier=MemoryTier.LTS,
        top_k=top_k,
        min_importance=0.2,
        since=since,
        tags_any=[domain] if domain else None,
    )
    lts_records = memory_fabric.recall(q_lts)
    
    # Combine and re-sort/limit
    all_records = sorted(mts_records + lts_records, key=lambda r: r.importance, reverse=True)
    return all_records[:top_k]
