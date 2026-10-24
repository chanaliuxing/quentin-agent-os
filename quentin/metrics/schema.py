from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Dict, Optional


@dataclass
class RunMetrics:
    """
    一次蓝皮书自迭代 run 的关键指标。

    注意：这里只是 v1，可以随着蓝皮书进化不断扩展字段。
    """

    # 基本信息
    run_id: str
    started_at: str
    finished_at: str

    # 蓝皮书能力覆盖情况
    total_capabilities: int
    num_done: int
    num_partial: int
    num_missing: int
    num_unknown: int

    # 实验数量 & 结果
    experiments_created: int
    experiments_executed: int
    experiments_succeeded: int
    experiments_failed: int
    experiments_rolled_back: int

    # Patch / 自编程（目前可能是 0，占位）
    patches_proposed: int
    patches_accepted: int
    patches_rolled_back: int

    # 资源消耗（如果 research_cycle_result 有这些字段就填，否则为 None）
    total_cost_tokens: Optional[float] = None
    total_cost_seconds: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
