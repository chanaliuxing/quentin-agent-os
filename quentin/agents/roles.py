from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict

from quentin.models.router import ModelRouter
from quentin.llm.client import call_llm


@dataclass
class AgentInput:
    role: str
    task_type: str
    domain: str
    prompt: str
    preference: str = "balanced"  # speed / cost / safety / ...
    meta: Dict[str, Any] = None


@dataclass
class AgentOutput:
    role: str
    model: str
    content: str
    meta: Dict[str, Any]


@dataclass
class BaseRoleAgent:
    """
    Role Agent 的基类。

    v1 不真正调用 LLM，只是给出接口：
    - choose_model：通过 ModelRouter 选模型
    - produce_output：一个占位的“回复”
    以后你可以在这里接入真实 LLM 调用。
    """

    name: str
    preference: str  # "speed" / "safety" / "cost" / ...

    async def run(self, router: ModelRouter, inp: AgentInput) -> AgentOutput:
        model_name = router.choose_model(
            task_type=inp.task_type,
            domain=inp.domain,
            preference=self.preference,
        ) or "unknown"

        meta = inp.meta or {}
        environment = str(meta.get("environment") or "sandbox")
        risk_level = str(meta.get("risk_level") or "medium")
        safety_kernel = meta.get("safety_kernel")

        # v2: real LLM call (guarded + audited via quentin.llm.client.call_llm)
        # Use ModelRouter.route() to map preference/task_type to provider/base_url.
        route_cfg = router.route(mode=self.preference, task_type=inp.task_type)
        try:
            content = call_llm(
                route_cfg,
                user_prompt=inp.prompt,
                system_prompt=(
                    f"You are {self.name}. Preference={self.preference}.\n"
                    "Return a concise, actionable answer.\n"
                ),
                safety_kernel=safety_kernel,
                actor=f"multi_agent::{self.name}",
                domain=str(inp.domain or "core"),
                environment=environment,
                risk_level=risk_level,
                action_metadata={
                    "multi_agent_role": self.name,
                    "preference": self.preference,
                    "task_type": inp.task_type,
                },
                provider=getattr(route_cfg, "provider", None),
                model_name=model_name,
            )
        except Exception as e:  # noqa: BLE001
            content = f"[{self.name}] error calling LLM: {e}"

        return AgentOutput(
            role=self.name,
            model=model_name,
            content=content,
            meta={"preference": self.preference},
        )


def default_roles() -> Dict[str, BaseRoleAgent]:
    """
    蓝皮书固定四个基础角色：
    - Speed-Agent
    - Safety-Agent
    - Cost-Agent
    - Domain-Expert-Agent
    """
    return {
        "speed": BaseRoleAgent(name="Speed-Agent", preference="speed"),
        "safety": BaseRoleAgent(name="Safety-Agent", preference="safety"),
        "cost": BaseRoleAgent(name="Cost-Agent", preference="cost"),
        "expert": BaseRoleAgent(name="Domain-Expert-Agent", preference="balanced"),
    }
