from __future__ import annotations

from typing import Dict, Any, Optional
from datetime import datetime
from pydantic import BaseModel, Field


class ModelUsageRecord(BaseModel):
    """
    一次 LLM / 模型路由调用的记录。
    未来用于：
      - 统计成功率 / 延迟 / 成本
      - 训练 bandit / routing 策略
    """
    usage_id: str
    task_id: Optional[str] = None
    domain: Optional[str] = None
    goal: Optional[str] = None

    # 真实调用信息
    model_name: str
    provider: str

    role: Optional[str] = None         # e.g. "planner", "critic", "self_programming"

    success: bool = True
    error: Optional[str] = None

    latency_sec: float = 0.0
    tokens_in: Optional[int] = None
    tokens_out: Optional[int] = None
    cost: Optional[float] = None       # 统一成 USD（后面可精算）

    reward: Optional[float] = None     # 自定义 reward（可由上层给）

    created_at: datetime = Field(default_factory=datetime.utcnow)
    meta: Dict[str, Any] = Field(default_factory=dict)

    model_config = {"protected_namespaces": ()}
