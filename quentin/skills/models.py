from __future__ import annotations

from dataclasses import dataclass, asdict, field
from typing import Any, Dict, Optional
from quentin.utils.time import now_iso


@dataclass
class SkillPerformanceStats:
    success_rate: float = 0.0
    usage_count: int = 0
    last_score: float = 0.0
    last_used_at: Optional[str] = None


@dataclass
class Skill:
    """
    v1 Skill 定义：

    - skill_id      : 全局唯一 ID
    - name          : 人类可读名字
    - domain        : 领域标签（"core" | "desktop" | "legal" | "trading" | "cross"）
    - module        : python module 路径
    - symbol        : 类名或函数名
    - description   : 这个技能做什么
    - origin        : "human" | "evolved"
    - safety_level  : "low" | "medium" | "high"
    - supersedes    : 被它取代的旧 skill_id（如有）
    """

    skill_id: str
    name: str
    domain: str
    module: str
    symbol: str
    description: str

    origin: str = "human"
    safety_level: str = "medium"
    supersedes: Optional[str] = None

    created_at: str = field(default_factory=lambda: now_iso())
    updated_at: str = field(default_factory=lambda: now_iso())

    performance_stats: SkillPerformanceStats = field(default_factory=SkillPerformanceStats)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["performance_stats"] = asdict(self.performance_stats)
        return d

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Skill":
        perf = d.get("performance_stats") or {}
        stats = SkillPerformanceStats(
            success_rate=float(perf.get("success_rate", 0.0)),
            usage_count=int(perf.get("usage_count", 0)),
            last_score=float(perf.get("last_score", 0.0)),
            last_used_at=perf.get("last_used_at"),
        )
        return cls(
            skill_id=d["skill_id"],
            name=d["name"],
            domain=d.get("domain", "core"),
            module=d["module"],
            symbol=d["symbol"],
            description=d.get("description", ""),
            origin=d.get("origin", "human"),
            safety_level=d.get("safety_level", "medium"),
            supersedes=d.get("supersedes"),
            created_at=d.get("created_at", ""),
            updated_at=d.get("updated_at", ""),
            performance_stats=stats,
            metadata=d.get("metadata", {}) or {},
        )

SkillCandidate = Skill
