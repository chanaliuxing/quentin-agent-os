from datetime import datetime, timedelta
from typing import Optional, Dict, Any

from quentin.memory.models import MemoryRecord, MemoryTier, MemoryUpdatePolicy
from quentin.utils.time import now_utc


class MemoryPolicyConfig:
    """
    一组默认阈值配置，后续可以通过 VariantConfig 注入不同版本。
    """

    def __init__(
        self,
        sts_to_mts_hits: int = 3,
        sts_to_mts_age_minutes: int = 30,
        mts_to_lts_hits: int = 10,
        mts_to_lts_age_days: int = 3,
        sts_ttl_minutes: int = 120,
        mts_ttl_days: int = 30,
    ):
        self.sts_to_mts_hits = sts_to_mts_hits
        self.sts_to_mts_age_minutes = sts_to_mts_age_minutes
        self.mts_to_lts_hits = mts_to_lts_hits
        self.mts_to_lts_age_days = mts_to_lts_age_days
        self.sts_ttl_minutes = sts_ttl_minutes
        self.mts_ttl_days = mts_ttl_days


class MemoryPolicyEngine:
    """
    负责解释 MemoryRecord.update_policy 里的 rule 名字，
    并根据当前配置给出 promotion / decay 决策。

    当前内置两套简单策略：
    - default_promotion_v1
    - default_decay_v1

    你可以在这里继续加别的 rule 名字，让 Research Layer 用 Variant 做实验。
    """

    def __init__(self, config: Optional[MemoryPolicyConfig] = None):
        self.config = config or MemoryPolicyConfig()

    # ---------- Promotion ----------

    def decide_promotion(
        self,
        rec: MemoryRecord,
        now: Optional[datetime] = None,
    ) -> Optional[MemoryTier]:
        """
        返回目标 tier，如果不需要升级则返回 None。
        """
        # Use timezone-aware UTC timestamps to avoid naive/aware subtraction errors.
        now = now or now_utc()
        rule = _policy_name(rec.update_policy, "promotion_rule", default="default_promotion_v1")

        if rule == "default_promotion_v1":
            return self._default_promotion(rec, now)

        # 预留其它 rule
        # if rule == "aggressive_promotion_v1": ...

        return None

    def _default_promotion(
        self,
        rec: MemoryRecord,
        now: datetime,
    ) -> Optional[MemoryTier]:
        cfg = self.config
        age = now - rec.created_at

        if _tier_value(rec) in (MemoryTier.STS.value, "STS"):
            if (
                rec.access_count >= cfg.sts_to_mts_hits
                and age >= timedelta(minutes=cfg.sts_to_mts_age_minutes)
            ):
                return MemoryTier.MTS

        if _tier_value(rec) in (MemoryTier.MTS.value, "MTS"):
            if (
                rec.access_count >= cfg.mts_to_lts_hits
                and age >= timedelta(days=cfg.mts_to_lts_age_days)
                and _importance(rec) >= 0.5
            ):
                return MemoryTier.LTS

        return None

    # ---------- Decay / Forgetting ----------

    def should_decay(
        self,
        rec: MemoryRecord,
        now: Optional[datetime] = None,
    ) -> bool:
        """
        返回 True 表示该条目应该被“衰减/删除/冷冻”。
        当前简单实现为“过期则删除”。
        """
        now = now or now_utc()
        rule = _policy_name(rec.update_policy, "decay_rule", default="default_decay_v1")

        if rule == "default_decay_v1":
            return self._default_decay(rec, now)

        # 预留其它规则
        return False

    def _default_decay(self, rec: MemoryRecord, now: datetime) -> bool:
        cfg = self.config
        last_accessed = _last_accessed_at(rec)
        age = now - last_accessed

        if _tier_value(rec) in (MemoryTier.STS.value, "STS"):
            return age > timedelta(minutes=cfg.sts_ttl_minutes)

        if _tier_value(rec) in (MemoryTier.MTS.value, "MTS"):
            return age > timedelta(days=cfg.mts_ttl_days)

        if _tier_value(rec) in (MemoryTier.LTS.value, "LTS"):
            # LTS 默认不自动删除，将来可以加“冷冻/压缩”逻辑
            return False

        return False


def _policy_name(
    policy: Optional[MemoryUpdatePolicy],
    key: str,
    default: str,
) -> str:
    if not policy:
        return default
    value = getattr(policy, key, None)
    if value is None:
        return default
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        for name_key in ("name", "rule", "id"):
            name = value.get(name_key)
            if name:
                return str(name)
    return default


def _importance(rec: MemoryRecord) -> float:
    value = getattr(rec, "importance", None)
    if value is None:
        value = getattr(rec, "strength", 0.0)
    try:
        return float(value)
    except Exception:
        return 0.0


def _last_accessed_at(rec: MemoryRecord) -> datetime:
    value = getattr(rec, "last_accessed_at", None)
    if value is None:
        value = getattr(rec, "last_access_at", None)
    if value is None:
        value = getattr(rec, "created_at", None)
    if isinstance(value, datetime):
        return value
    return now_utc()


def _tier_value(rec: MemoryRecord) -> str:
    tier = getattr(rec, "tier", "")
    if hasattr(tier, "value"):
        return str(tier.value)
    return str(tier)
