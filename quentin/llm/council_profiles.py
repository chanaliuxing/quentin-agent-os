from __future__ import annotations

from typing import List
from quentin.llm.types import LLMConfig
from quentin.llm.multi_council import MultiAICouncil
from quentin.llm.router import ModelRouter


def make_decision_council(
    *,
    router: ModelRouter,
    domain: str,
    mode: str,
) -> MultiAICouncil:
    """
    构造一个带 4 个角色的 MultiAICouncil：

    - Speed-Agent         : 偏向速度（router 决定）
    - Safety-Agent        : 偏向安全性/保守
    - Cost-Agent          : 偏向省 token（可以与 Speed 复用）
    - Domain-Expert-Agent : 偏领域知识（如 legal/trading/domain-specific）

    v1 简化实现：都通过 ModelRouter 拿模型，只是 role 不同，
    以后可以在 router.rules 中对不同 role 做更细粒度配置。
    """
    domain = domain.lower()
    mode = mode.lower()

    # Speed-Agent
    cfg_speed = router.route(mode=mode, task_type=domain)
    speed = LLMConfig(
        provider=cfg_speed.provider,
        model=cfg_speed.model,
        role=f"speed_agent::{mode}::{domain}",
    )

    # Safety-Agent（目前复用 qwen，等以后可以切换安全向模型）
    cfg_safety = router.route(mode="critic", task_type=domain)
    safety = LLMConfig(
        provider=cfg_safety.provider,
        model=cfg_safety.model,
        role=f"safety_agent::{mode}::{domain}",
    )

    # Cost-Agent（暂时和 speed 一样，未来可以切 ultra-small 模型）
    cfg_cost = router.route(mode=mode, task_type=domain)
    cost = LLMConfig(
        provider=cfg_cost.provider,
        model=cfg_cost.model,
        role=f"cost_agent::{mode}::{domain}",
    )

    # Domain-Expert-Agent（同样通过 router，让 router 可以以后绑定专用模型）
    cfg_domain = router.route(mode=mode, task_type=domain)
    expert = LLMConfig(
        provider=cfg_domain.provider,
        model=cfg_domain.model,
        role=f"domain_expert_agent::{mode}::{domain}",
    )

    members: List[LLMConfig] = [speed, safety, cost, expert]
    return MultiAICouncil(members=members)
