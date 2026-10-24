from __future__ import annotations

from datetime import datetime, UTC
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class ExperimentStatus(str, Enum):
    pending = "pending"
    running = "running"
    completed = "completed"
    failed = "failed"
    cancelled = "cancelled"


class ExperimentVariant(BaseModel):
    """
    一个 Variant 就是一种“算法/策略配置”的版本。
    例如：
    - 不同的 planner 提示词
    - 不同的模型路由策略
    - 不同的工具组合
    """
    variant_id: str
    name: str
    params: Dict[str, Any] = Field(default_factory=dict)


class ExperimentConfig(BaseModel):
    """
    定义实验的目标和范围：
    - target_module / target_kind：比如 "planner", "router"
    - metrics：我们关心的指标名称
    """
    target_module: str
    target_kind: Optional[str] = None
    metrics: List[str] = Field(default_factory=list)
    traffic_fraction: float = 0.1  # 在线实验时，可用来控制流量
    meta: Dict[str, Any] = Field(default_factory=dict)


class ExperimentRecord(BaseModel):
    experiment_id: str
    name: str
    description: str = ""
    config: ExperimentConfig
    variants: List[ExperimentVariant]

    status: ExperimentStatus = ExperimentStatus.pending

    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    # 简单的聚合结果：可以是每个 variant 的指标对比
    results: Dict[str, Any] = Field(default_factory=dict)

    meta: Dict[str, Any] = Field(default_factory=dict)
