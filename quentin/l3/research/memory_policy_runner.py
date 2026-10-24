from typing import Dict, Any

from quentin.experiments.schemas import VariantConfig
from quentin.eval.harness import EvalCaseResult
from quentin.memory.fabric import MemoryFabric
from quentin.memory.models import MemoryTier
from quentin.memory.adapters import kernel_dict_to_memory_record
from quentin.memory.policies import MemoryPolicyConfig, MemoryPolicyEngine
from quentin.utils.time import now_utc


async def memory_policy_runner(
    variant: VariantConfig,
    case_input: Dict[str, Any],
) -> EvalCaseResult:
    """
    用于 EvalHarness 的 Runner (kind="memory_policy") 示例骨架：

    case_input 约定格式（你可以根据需要调整/扩展）：
    {
       "initial_records": [MemoryRecord.model_dump(), ...],
       "access_events": [
           {"memory_id": "...", "timestamp": "... isoformat ...", "strength_delta": 0.1},
           ...
       ]
    }

    逻辑：
    1) 用 variant.params 构建一套 MemoryPolicyConfig
    2) 在一个临时 MemoryFabric 上重放 initial_records + access_events
    3) 调用 run_consolidation()
    4) 统计例如：升到 LTS 的条目数量、删除数量等
    5) 根据目标指标打一个 score 返回
    """

    # 1) 从 variant.params 读取配置（带默认值）
    p = variant.params or {}
    cfg = MemoryPolicyConfig(
        sts_to_mts_hits=p.get("sts_to_mts_hits", 3),
        sts_to_mts_age_minutes=p.get("sts_to_mts_age_minutes", 30),
        mts_to_lts_hits=p.get("mts_to_lts_hits", 10),
        mts_to_lts_age_days=p.get("mts_to_lts_age_days", 3),
        sts_ttl_minutes=p.get("sts_ttl_minutes", 120),
        mts_ttl_days=p.get("mts_ttl_days", 30),
    )

    fabric = MemoryFabric()
    policy_engine = MemoryPolicyEngine(cfg)

    # 2) 重放 initial_records
    initial_records = case_input.get("initial_records") or []
    for r_data in initial_records:
        rec = kernel_dict_to_memory_record(r_data)
        fabric.store.add(rec)

    # 3) 重放 access_events
    events = case_input.get("access_events") or []
    now = now_utc()
    for e in events:
        mem_id = e["memory_id"]
        strength_delta = e.get("strength_delta", 0.0)
        rec = fabric.store.get(mem_id)
        if rec is None:
            continue
        rec.access_count += 1
        rec.importance = max(0.0, float(rec.importance) + float(strength_delta))
        rec.last_accessed_at = now
        fabric.store.update(rec)

    # 4) consolidation
    deleted = 0
    promoted = 0
    for tier in (MemoryTier.STS, MemoryTier.MTS, MemoryTier.LTS):
        records = fabric.store.get_candidates_for_consolidation(tier=tier, limit=5000)
        for rec in records:
            target = policy_engine.decide_promotion(rec, now=now)
            if target is not None and target != rec.tier:
                fabric.store.promote(rec.id, target)
                promoted += 1
            if policy_engine.should_decay(rec, now=now):
                fabric.store.mark_decayed(rec.id)
                deleted += 1

    # 5) 统计结果（示例：希望“提升到 LTS 的数量最多，删除数量适中”）
    stats = {MemoryTier.STS.value: 0, MemoryTier.MTS.value: 0, MemoryTier.LTS.value: 0}
    for tier in (MemoryTier.STS, MemoryTier.MTS, MemoryTier.LTS):
        stats[tier.value] = len(fabric.store.get_candidates_for_consolidation(tier=tier, limit=5000))
    lts_count = stats.get(MemoryTier.LTS.value, 0)

    # 非常简单的 scoring 逻辑：多 LTS 少删除 → score 更高
    score = float(lts_count) - 0.1 * float(deleted)
    success = score > 0

    return EvalCaseResult(
        case_id=str(case_input.get("case_id") or ""),
        variant_id=variant.variant_id,
        success=1.0 if success else 0.0,
        status="success",
        latency_sec=None,
        raw_metrics={
            "lts_count": lts_count,
            "deleted": deleted,
            "promoted": promoted,
            "tier_stats": stats,
        },
        notes="",
    )
