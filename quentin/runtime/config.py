from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Dict


@dataclass
class LoopBudgetConfig:
    """
    控制各个循环的大致资源预算（v1 用于提示 / logging）。
    """
    max_traces_per_sleep: int = 100
    max_traces_per_immune_scan: int = 200


@dataclass
class CouncilPolicyConfig:
    """
    多 AI 开会 / 合议模式的策略。

    这里只是配置，不直接实现逻辑；
    具体什么时候真的开会，由 orchestrator / planner 解释这些字段。
    """
    # 对“任务级别”的控制
    enable_for_critical_tasks: bool = True
    enable_for_long_running_tasks: bool = True

    # 对“阶段”的控制
    use_for_planning: bool = True           # 做计划时启用多模 deliberation
    use_for_reflection: bool = True        # 反思 / 总结时启用合议
    use_for_coding_retries: bool = True    # 编程多次失败时触发合议

    # 简单阈值（交给上层解释）
    coding_retry_council_threshold: int = 2   # 连续失败 >= 2 次就开会


@dataclass
class RuntimeConfig:
    """
    RuntimeFacade 的顶层配置。
    """
    loop_budget: LoopBudgetConfig = field(default_factory=LoopBudgetConfig)
    council_policy: CouncilPolicyConfig = field(default_factory=CouncilPolicyConfig)

    # 将来可以在这里挂：
    # - 安全策略（宪法 id）
    # - 日志级别
    # - 默认模型路由策略 id 等
    extra: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        return d
