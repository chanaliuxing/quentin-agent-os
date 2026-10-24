# quentin/memory/schemas.py
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Dict, Any, List, Literal, Optional
from quentin.utils.time import now_utc

MemoryTier = Literal["STS", "MTS", "LTS"]
MemoryKind = Literal["episodic", "semantic", "skill", "meta"]

@dataclass
class MemoryUpdatePolicy:
    """
    对应蓝皮书里的 update_policy：
    - promotion_rule   : STS/MTS 升级条件的文字描述（后续可以变成可执行规则）
    - decay_rule       : 何时衰减/删除
    - consolidation_batch: nightly / weekly / manual
    v1 先存字符串，方便人/AI读；真正的逻辑在 Sleep Loop 里实现。
    """
    promotion_rule: str = ""
    decay_rule: str = ""
    consolidation_batch: str = "nightly"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MemoryUpdatePolicy":
        return cls(
            promotion_rule=data.get("promotion_rule", ""),
            decay_rule=data.get("decay_rule", ""),
            consolidation_batch=data.get("consolidation_batch", "nightly"),
        )


@dataclass
class MemoryEntry:
    """
    Memory Fabric v1 的核心数据结构。

    对齐蓝皮书：
    - memory_tier : STS/MTS/LTS
    - kind        : episodic/semantic/skill/meta
    - content     : 统一放在一个 dict 里，至少有 'text' 字段；以后可以再加 'json'/'trace_ref'
    - importance  : 0~1，重要程度
    - usage_count : 被命中/使用次数（用于 Sleep Loop）
    - last_accessed_at: 上次被访问时间
    - update_policy  : promotion/decay 规则描述
    """
    memory_id: str
    memory_tier: MemoryTier
    kind: MemoryKind

    content: Dict[str, Any] = field(default_factory=dict)

    created_at: str = field(default_factory=lambda: now_utc().isoformat())
    updated_at: str = field(default_factory=lambda: now_utc().isoformat())
    last_accessed_at: Optional[str] = None

    importance: float = 0.5
    usage_count: int = 0

    source: str = "unknown"                # e.g. "task_execution", "sleep_consolidation"
    tags: List[str] = field(default_factory=list)
    relations: Dict[str, float] = field(default_factory=dict)  # memory_id -> weight

    update_policy: MemoryUpdatePolicy = field(default_factory=MemoryUpdatePolicy)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        # dataclasses 已经递归展开 update_policy
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MemoryEntry":
        upd = data.get("update_policy", {})
        policy = MemoryUpdatePolicy.from_dict(upd)
        return cls(
            memory_id=data["memory_id"],
            memory_tier=data.get("memory_tier", "STS"),
            kind=data.get("kind", "episodic"),
            content=data.get("content", {}),
            created_at=data.get("created_at", ""),
            updated_at=data.get("updated_at", ""),
            last_accessed_at=data.get("last_accessed_at"),
            importance=float(data.get("importance", 0.5)),
            usage_count=int(data.get("usage_count", 0)),
            source=data.get("source", "unknown"),
            tags=list(data.get("tags", [])),
            relations=dict(data.get("relations", {})),
            update_policy=policy,
        )
