from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Dict, Any, List, Optional
from quentin.utils.time import now_utc


TASK_STATUS_PENDING = "pending"
TASK_STATUS_IN_PROGRESS = "in_progress"
TASK_STATUS_DONE = "done"
TASK_STATUS_ABANDONED = "abandoned"

# 优先级越小越先做（1 > 2 > 3）
PRIORITY_HIGH = 1      # overall_status = missing
PRIORITY_MEDIUM = 2    # overall_status = placeholder / partial
PRIORITY_LOW = 3       # overall_status = implemented，但仍有优化空间（后面再用）


@dataclass
class ImprovementTask:
    """
    自我改进任务：
    由 BlueprintGapTracker 的结果生成，
    用来驱动 SelfProgrammingEngine / MultiLLMCouncil 等模块做演化。
    """
    task_id: str
    capability: str                # e.g. "memory_fabric"
    requirement_id: Optional[str]  # e.g. "mf.search_semantic"（有些可能是 None）
    overall_status: str            # 能力当前状态：missing / placeholder / partial / implemented
    status: str = TASK_STATUS_PENDING
    priority: int = PRIORITY_MEDIUM
    title: str = ""
    description: str = ""
    created_at: str = field(default_factory=lambda: now_utc().isoformat())
    updated_at: str = field(default_factory=lambda: now_utc().isoformat())
    meta: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ImprovementTask":
        return cls(**data)

    @property
    def key(self) -> str:
        """
        一个稳定的逻辑主键:
        capability + requirement_id (如果有的话)
        """
        if self.requirement_id:
            return f"{self.capability}:{self.requirement_id}"
        return self.capability
