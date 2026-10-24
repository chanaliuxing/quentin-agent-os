from __future__ import annotations

from typing import Dict, Any, List, Optional
from datetime import datetime
from pydantic import BaseModel, Field


class ExecutionStep(BaseModel):
    """
    单个执行步骤：
    - kind: "domain_task" / "tool_call" / "model_call" / ...
    - name: 例如 "generic.handle_task" / "generic.echo"
    """
    step_id: str
    kind: str
    name: str

    input: Dict[str, Any] = Field(default_factory=dict)
    output: Optional[Dict[str, Any]] = None
    error: Optional[str] = None

    started_at: datetime = Field(default_factory=datetime.utcnow)
    finished_at: Optional[datetime] = None

    success: bool = True

    meta: Dict[str, Any] = Field(default_factory=dict)


class ExecutionTrace(BaseModel):
    """
    一次任务执行的完整 Trace（多步）。
    """
    trace_id: str
    task_id: str
    domain: str
    goal: str
    task_input: Dict[str, Any] = Field(default_factory=dict)

    started_at: datetime = Field(default_factory=datetime.utcnow)
    finished_at: Optional[datetime] = None

    steps: List[ExecutionStep] = Field(default_factory=list)

    success: bool = True
    error: Optional[str] = None

    metrics: Dict[str, Any] = Field(default_factory=dict)
    meta: Dict[str, Any] = Field(default_factory=dict)


class ExecutionSummary(BaseModel):
    """
    Trace 的压缩版本，给记忆 / 评测 / 运维看。
    """
    summary_id: str
    trace_id: str
    task_id: str
    domain: str
    goal: str

    success: bool
    error: Optional[str] = None

    steps_count: int
    started_at: datetime
    finished_at: datetime

    # 粗粒度指标（后续可以补 token / cost / reward 等）
    metrics: Dict[str, Any] = Field(default_factory=dict)

    # 与 lessons_learned 在 MemoryFabric 中的链接
    lesson_memory_ids: List[str] = Field(default_factory=list)

    meta: Dict[str, Any] = Field(default_factory=dict)


class CriticReview(BaseModel):
    """
    Critic 对一次 Trace 的总结。
    - summary: 人类可读的一句话总结
    - lessons: 若干条可写入记忆的经验教训
    """
    summary: str
    lessons: List[str] = Field(default_factory=list)
    meta: Dict[str, Any] = Field(default_factory=dict)
