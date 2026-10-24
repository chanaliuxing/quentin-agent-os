from __future__ import annotations

import json
from typing import Any, Dict

from quentin.kernel.schemas import MemoryRecord as KernelMemoryRecord
from quentin.kernel.schemas import MemoryTier as KernelMemoryTier
from quentin.memory.models import MemoryRecord, MemoryTier, MemoryUpdatePolicy
from quentin.utils.time import now_utc


_KERNEL_TIER_MAP = {
    "STS": MemoryTier.STS,
    "MTS": MemoryTier.MTS,
    "LTS": MemoryTier.LTS,
}


def kernel_record_to_memory_record(record: KernelMemoryRecord) -> MemoryRecord:
    content = record.content if isinstance(record.content, str) else json.dumps(record.content, ensure_ascii=False)
    tier = _KERNEL_TIER_MAP.get(str(record.tier), MemoryTier.STS)
    update_policy = MemoryUpdatePolicy(
        promotion_rule={"name": record.update_policy.promotion_rule} if record.update_policy else None,
        decay_rule={"name": record.update_policy.decay_rule} if record.update_policy else None,
        consolidation_batch={"name": record.update_policy.consolidation_batch} if record.update_policy else None,
    )
    return MemoryRecord(
        id=record.memory_id,
        tier=tier,
        content=content,
        created_at=record.created_at,
        updated_at=record.created_at,
        source="kernel_record",
        domain=record.domain,
        importance=float(getattr(record, "strength", 0.0)),
        last_accessed_at=record.last_access_at,
        access_count=record.access_count,
        tags=list((record.metadata or {}).get("tags") or []),
        metadata=record.metadata or {},
        update_policy=update_policy,
    )


def kernel_dict_to_memory_record(payload: Dict[str, Any]) -> MemoryRecord:
    if "memory_id" in payload:
        record = KernelMemoryRecord(**payload)
        return kernel_record_to_memory_record(record)
    return MemoryRecord(**payload)


def memory_record_to_kernel_record(record: MemoryRecord) -> KernelMemoryRecord:
    tier = KernelMemoryTier.STS
    if record.tier == MemoryTier.MTS:
        tier = KernelMemoryTier.MTS
    elif record.tier == MemoryTier.LTS:
        tier = KernelMemoryTier.LTS
    update_policy = None
    if record.update_policy:
        update_policy = {
            "promotion_rule": record.update_policy.promotion_rule,
            "decay_rule": record.update_policy.decay_rule,
            "consolidation_batch": record.update_policy.consolidation_batch,
        }
    return KernelMemoryRecord(
        memory_id=record.id,
        tier=tier,
        content=record.content,
        domain=record.domain or "generic",
        metadata=record.metadata or {},
        created_at=record.created_at,
        last_access_at=record.last_accessed_at or now_utc(),
        access_count=record.access_count,
        strength=record.importance,
        update_policy=update_policy,
    )
