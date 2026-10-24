from __future__ import annotations

from typing import Dict, Any, List, Optional
from datetime import datetime
from enum import Enum
from pydantic import BaseModel, Field


class ImmuneCaseStatus(str, Enum):
    open = "open"
    investigating = "investigating"
    mitigated = "mitigated"
    ignored = "ignored"
    closed = "closed" # New status


class ImmuneCase(BaseModel):
    """
    Immune Loop 发现的“异常事件包”：
    - 一段时间内 error / latency 等异常
    - 对应的 trace_id 列表
    - 后续可以被 Research Layer / 自编程引擎使用
    """
    case_id: str

    title: Optional[str] = None # New
    description: Optional[str] = None # New
    domain: Optional[str] = None # New
    tags: List[str] = Field(default_factory=list) # New
    metrics: Dict[str, float] = Field(default_factory=dict) # New (merged with existing logic if possible, or just use this)

    window_start: Optional[datetime] = None # Made optional for single-event cases
    window_end: Optional[datetime] = None # Made optional

    trace_ids: List[str] = Field(default_factory=list) # Renamed from traces in ai/33 but kept for compatibility
    traces: List[str] = Field(default_factory=list) # Alias for trace_ids or separate? ai/33 uses traces. I'll keep both or sync.
    error_trace_ids: List[str] = Field(default_factory=list)

    # 聚合指标
    total_tasks: int = 0
    error_tasks: int = 0
    avg_latency_sec: float = 0.0

    # 暂时用字符串列表占位，后续可以换成结构化 suspects
    suspected_modules: List[str] = Field(default_factory=list)

    status: ImmuneCaseStatus = ImmuneCaseStatus.open
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow) # New
    meta: Dict[str, Any] = Field(default_factory=dict)
