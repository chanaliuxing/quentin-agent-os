from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List

from quentin.models.router import ModelRouter
from quentin.agents.roles import AgentInput, AgentOutput, BaseRoleAgent, default_roles


@dataclass
class MultiAgentCoordinator:
    """
    Multi-Agent 协调器 v1：

    - 给定一个任务（AgentInput），调用多个角色 Agent
    - 返回所有视角 + 一个简单的 aggregate 结果

    以后你可以在这里实现：
    - debate 式交互（多轮）
    - 自定义聚合策略（多数表决 / 加权投票 / 通过 Critic 评分）
    """

    router: ModelRouter
    roles: Dict[str, BaseRoleAgent]

    @classmethod
    def with_default_roles(cls, router: ModelRouter) -> "MultiAgentCoordinator":
        return cls(router=router, roles=default_roles())

    async def run_multi_view(self, inp: AgentInput) -> Dict[str, Any]:
        outputs: List[AgentOutput] = []

        for key, agent in self.roles.items():
            out = await agent.run(self.router, inp)
            outputs.append(out)

        # v1 简单聚合：选第一个作为 final
        final = outputs[0] if outputs else None

        return {
            "final": final,
            "views": [o.__dict__ for o in outputs],
        }
