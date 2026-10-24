# quentin/eval/spec.py
from __future__ import annotations

from dataclasses import dataclass, asdict, field
from typing import Any, Dict, List, Optional


@dataclass
class EvalTaskSpec:
    """
    单个评测任务（一个“样本”）。

    举例：
    - 对 planner：给定 goal / context，期望拆成多少步、大致结构
    - 对 model_router：给定任务特征，期望选择哪个模型、成本范围等
    """
    task_id: str
    description: str
    component: str              # "planner" / "model_router" / "skill_evolution" 等
    input_payload: Dict[str, Any] = field(default_factory=dict)
    expected_output: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class EvalDatasetSpec:
    """
    一组 EvalTask 的集合（一个评测数据集）。
    """
    dataset_id: str
    name: str
    description: str
    component: str                      # 针对哪个组件
    tasks: List[EvalTaskSpec] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["tasks"] = [t.to_dict() for t in self.tasks]
        return d


@dataclass
class EvalCaseResult:
    """
    单个任务的评测结果。
    """
    task_id: str
    variant_id: str
    success: bool
    score: float
    raw_output: Dict[str, Any] = field(default_factory=dict)
    notes: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
