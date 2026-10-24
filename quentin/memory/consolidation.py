# quentin/memory/consolidation.py
from __future__ import annotations

import logging
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional

from quentin.memory.fabric import MemoryFabric
from quentin.memory.schemas import MemoryEntry, MemoryTier
from quentin.utils.time import now_iso, now_utc, normalize_to_utc_iso

logger = logging.getLogger(__name__)


@dataclass
class SleepConsolidationConfig:
    """
    Sleep Loop 的阈值配置：

    - sts_to_mts_min_usage      : STS -> MTS 最小 usage_count
    - sts_to_mts_min_importance : STS -> MTS 最小 importance
    - sts_decay_days            : STS 存活天数（超过且使用很少则删除）

    - mts_to_lts_min_usage      : MTS -> LTS 最小 usage_count
    - mts_to_lts_min_importance : MTS -> LTS 最小 importance
    - mts_min_age_days          : MTS -> LTS 最小存活天数
    """
    sts_to_mts_min_usage: int = 3
    sts_to_mts_min_importance: float = 0.6
    sts_decay_days: int = 7

    mts_to_lts_min_usage: int = 10
    mts_to_lts_min_importance: float = 0.7
    mts_min_age_days: int = 7

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class SleepLoopResult:
    """
    Sleep Loop 一次运行后的结果统计。
    """
    promoted_sts_to_mts: int = 0
    promoted_mts_to_lts: int = 0
    deleted_sts: int = 0

    processed_sts: int = 0
    processed_mts: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class SleepLoop:
    """
    Sleep / Consolidation Loop v1：

    - 每次运行：
      1. 扫描 STS，决定哪些升级到 MTS，哪些删除
      2. 扫描 MTS，决定哪些升级到 LTS

    v1 的逻辑完全是 heuristics，可以之后通过 Self-Programming 再迭代。
    """

    def __init__(
        self,
        fabric: Optional[MemoryFabric] = None,
        config: Optional[SleepConsolidationConfig] = None,
    ) -> None:
        self.fabric = fabric or MemoryFabric()
        self.config = config or SleepConsolidationConfig()

    # ---------- 主入口 ----------

    def run_once(self) -> SleepLoopResult:
        result = SleepLoopResult()
        now = now_utc()

        # 1) 处理 STS
        sts_entries = self.fabric.store.list_by_tier("STS")  # type: ignore[arg-type]
        for e in sts_entries:
            result.processed_sts += 1
            if self._should_promote_sts_to_mts(e):
                self._promote(e, "MTS")
                result.promoted_sts_to_mts += 1
            elif self._should_decay_sts(e, now):
                self.fabric.delete(e.memory_id)
                result.deleted_sts += 1

        # 2) 处理 MTS
        mts_entries = self.fabric.store.list_by_tier("MTS")  # type: ignore[arg-type]
        for e in mts_entries:
            result.processed_mts += 1
            if self._should_promote_mts_to_lts(e, now):
                self._promote(e, "LTS")
                result.promoted_mts_to_lts += 1

        logger.info(
            "SleepLoop finished: %s",
            result.to_dict(),
        )
        return result

    # ---------- 内部规则 ----------

    def _should_promote_sts_to_mts(self, e: MemoryEntry) -> bool:
        cfg = self.config
        if e.usage_count >= cfg.sts_to_mts_min_usage and e.importance >= cfg.sts_to_mts_min_importance:
            return True
        return False

    def _should_decay_sts(self, e: MemoryEntry, now: datetime) -> bool:
        cfg = self.config
        # 如果根本没被访问过，则视 last_accessed_at 为 created_at
        last_ts_str = e.last_accessed_at or e.created_at
        try:
            last_ts = datetime.fromisoformat(normalize_to_utc_iso(last_ts_str))
        except Exception:
            return False

        age_days = (now - last_ts).days
        if age_days >= cfg.sts_decay_days and e.usage_count <= 1 and e.importance < 0.5:
            return True
        return False

    def _should_promote_mts_to_lts(self, e: MemoryEntry, now: datetime) -> bool:
        cfg = self.config
        try:
            created_ts = datetime.fromisoformat(normalize_to_utc_iso(e.created_at))
        except Exception:
            return False

        age_days = (now - created_ts).days
        if (
            e.usage_count >= cfg.mts_to_lts_min_usage
            and e.importance >= cfg.mts_to_lts_min_importance
            and age_days >= cfg.mts_min_age_days
        ):
            return True
        return False

    def _promote(self, e: MemoryEntry, new_tier: MemoryTier) -> None:
        e.memory_tier = new_tier
        e.updated_at = now_iso()
        self.fabric.update(e)
