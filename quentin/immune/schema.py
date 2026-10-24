from __future__ import annotations

from dataclasses import dataclass, asdict, field
from typing import Any, Dict, List, Optional
from quentin.utils.time import now_iso


@dataclass
class ImmuneSignal:
    """
    单个异常信号（来自某次任务或某一段时间）。
    比如：
    - 某个 skill 的失败率异常升高
    - 某个模型的成本突然飙升
    """
    signal_id: str
    source: str                     # "trace" / "metrics" / "manual"
    component: str                  # "planner" / "executor" / "model_router" / "skill" / ...
    key: str                        # 关键标识，如 skill_id / model_id
    severity: str                   # "low" / "medium" / "high" / "critical"
    metrics: Dict[str, Any] = field(default_factory=dict)
    context: Dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=now_iso)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ImmuneCase:
    """
    免疫案例：把一堆异常信号汇总成一个“问题模块”。

    这个对象会：
    - 交给 ResearchLayer 生成 Experiment
    - 交给 SelfProgrammingEngine 生成 PatchCandidate
    """
    case_id: str
    component: str
    target: Dict[str, Any]          # 目标描述 {target_type, identifier, file_path, symbol_name...}
    severity: str
    signals: List[ImmuneSignal] = field(default_factory=list)

    summary: str = ""
    suggested_actions: List[str] = field(default_factory=list)
    created_at: str = field(default_factory=now_iso)
    created_by: str = "immune_loop"

    meta: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["signals"] = [s.to_dict() for s in self.signals]
        return d
