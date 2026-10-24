from __future__ import annotations

from dataclasses import dataclass, asdict, field
from typing import Any, Dict, List, Optional
from quentin.utils.time import now_iso


@dataclass
class StepTrace:
    """
    单步执行轨迹（比如 planner / executor 的一步）。
    """
    step_id: str
    role: str                   # "planner" / "executor" / "critic" / "router" / ...
    action: str                 # 人类可读，如 "plan_subtasks" / "call_tool" / "route_model"
    input: Dict[str, Any] = field(default_factory=dict)
    output: Dict[str, Any] = field(default_factory=dict)
    metrics: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None
    started_at: Optional[str] = None
    finished_at: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ExecutionTrace:
    """
    一次完整任务的轨迹（Cognitive Loop 的执行结果）。
    """
    trace_id: str
    task_id: str
    domain: str                      # "general" / "desktop" / "legal" / "trading" ...
    status: str                      # "success" / "failed" / "partial" / "cancelled"
    steps: List[StepTrace] = field(default_factory=list)

    created_at: str = field(default_factory=now_iso)
    execution_summary: Dict[str, Any] = field(default_factory=dict)
    lessons_learned: Dict[str, Any] = field(default_factory=dict)
    top_level_metrics: Dict[str, Any] = field(default_factory=dict)

    meta: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["steps"] = [s.to_dict() for s in self.steps]
        return d
