from __future__ import annotations

from typing import Dict, Any, List, Optional
from datetime import datetime
from enum import Enum
from pydantic import BaseModel, Field


class ExperimentStatus(str, Enum):
    draft = "draft"
    running = "running"
    completed = "completed"
    failed = "failed"
    cancelled = "cancelled"


class ExperimentRunStatus(str, Enum):
    pending = "pending"
    running = "running"
    succeeded = "succeeded"
    failed = "failed"


class VariantConfig(BaseModel):
    """
    一个“变体”的定义：
    - kind: 如 "model_router" / "planner" / "skill" / "generic"
    - params: 变体的超参数（交给具体模块去解释）
    """
    variant_id: str
    label: Optional[str] = None
    description: Optional[str] = None

    kind: str = "generic"
    params: Dict[str, Any] = Field(default_factory=dict)
    meta: Dict[str, Any] = Field(default_factory=dict)


class ExperimentConfig(BaseModel):
    """
    用来“申请创建实验”的配置：
    - 不含状态，只描述：评测方式 + 变体们 + 数据集等
    """
    name: str
    description: Optional[str] = None

    eval_kind: str = "offline"          # offline / online / custom
    dataset: Optional[str] = None       # 比如 "desktop_small", "legal_dev_set"

    variants: List[VariantConfig]

    meta: Dict[str, Any] = Field(default_factory=dict)

    # 可选指定 experiment_id，否则由系统生成
    experiment_id: Optional[str] = None


class ExperimentRunResult(BaseModel):
    """
    某一次 (experiment, variant) 组合的评测结果。
    """
    run_id: str
    experiment_id: str
    variant_id: str

    status: ExperimentRunStatus = ExperimentRunStatus.succeeded

    metrics: Dict[str, Any] = Field(default_factory=dict)
    error: Optional[str] = None

    started_at: datetime = Field(default_factory=datetime.utcnow)
    finished_at: Optional[datetime] = None

    meta: Dict[str, Any] = Field(default_factory=dict)


class ExperimentRecord(BaseModel):
    """
    持久化在 KV 里的实验记录：
    - = ExperimentConfig + 状态 + runs
    """
    experiment_id: str
    name: str
    description: Optional[str] = None

    eval_kind: str
    dataset: Optional[str] = None
    variants: List[VariantConfig]

    status: ExperimentStatus = ExperimentStatus.draft

    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    runs: List[ExperimentRunResult] = Field(default_factory=list)

    meta: Dict[str, Any] = Field(default_factory=dict)
