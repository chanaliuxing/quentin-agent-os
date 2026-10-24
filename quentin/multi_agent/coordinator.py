from __future__ import annotations

from dataclasses import dataclass
from typing import List, Dict, Any, Optional
import os

from quentin.infra.logging import Tracer
from quentin.routing.model_router import ModelRouter
from quentin.multi_agent.schemas import AgentRole, RoleVote, RoutingDecision
from quentin.config.settings import Settings


from quentin.multi_agent.roles import BaseAgentRole, SpeedAgent, CostAgent, SafetyAgent, DomainExpertAgent


@dataclass
class MultiAgentCoordinator:
    """
    Multi-Agent Coordinator v2：

    输入：
      - candidate_models: ["gpt-4", "deepseek-r1", ...]
      - task_meta: {domain, goal, role, ...}

    输出：
      - RoutingDecision: chosen_model + 各角色投票详情

    当前实现：
      - 动态注册 AgentRole
      - 利用 ModelRouter 的 get_stats() 做简单“数据驱动”
    """
    tracer: Tracer
    model_router: ModelRouter
    settings: Settings
    roles: List[BaseAgentRole]

    def __init__(
        self,
        tracer: Tracer,
        model_router: ModelRouter,
        settings: Settings,
        roles: Optional[List[BaseAgentRole]] = None,
    ):
        self.tracer = tracer
        self.model_router = model_router
        self.settings = settings
        if roles is None:
            # Provide default roles if none are specified
            self.roles = [
                SpeedAgent(),
                CostAgent(),
                SafetyAgent(),
                DomainExpertAgent(),
            ]
        else:
            self.roles = roles

    async def _get_recent_stats(self) -> Dict[str, Any]:
        return await self.model_router.get_stats(limit=1000)

    def _get_model_stat(
        self,
        stats: Dict[str, Any],
        model_name: str,
    ) -> Dict[str, Any]:
        for m in stats.get("models", []):
            if m["model_name"] == model_name:
                return m
        return {
            "model_name": model_name,
            "calls": 0,
            "success_rate": 0.0,
            "avg_latency_sec": 0.0,
            "avg_cost": None,
        }

    async def choose_model(
        self,
        candidates: List[str],
        task_meta: Optional[Dict[str, Any]] = None,
    ) -> RoutingDecision:
        """
        Multi-Agent 总入口：

        - 输入候选模型 + 任务元信息
        - 输出最终选择 + 角色投票详情
        """
        task_meta = task_meta or {}
        domain = task_meta.get("domain")
        is_subagent = bool(task_meta.get("is_subagent", False))
        prompt_mode = "minimal" if is_subagent else "full"

        stats = await self._get_recent_stats()
        model_stats: Dict[str, Dict[str, Any]] = {
            m: self._get_model_stat(stats, m) for m in candidates
        }

        all_votes: List[RoleVote] = []
        for role in self.roles:
            all_votes.extend(role.vote(model_stats, candidates, task_meta, self.settings))

        agg: Dict[str, float] = {m: 0.0 for m in candidates}
        for v in all_votes:
            role_weight = next((role.weight for role in self.roles if role.role == v.role), 1.0)
            agg[v.model_name] += v.score * role_weight

        chosen_model = max(agg.items(), key=lambda kv: kv[1])[0] if agg else candidates[0]

        decision = RoutingDecision(
            chosen_model=chosen_model,
            votes=all_votes,
            meta={
                "scores": agg,
                "task_meta": task_meta,
                "prompt_mode": prompt_mode,
            },
        )

        self.tracer.span(
            "L2",
            "multi_agent_choose_model",
            module="multi_agent",
            input={"candidates": candidates, "domain": domain},
            output={"chosen_model": chosen_model},
        )

        repo_root = str(task_meta.get("repo_root") or ".")
        session_id = str(task_meta.get("session_id") or "brain")

        # Optional persistence into MemoryFabric for cross-session recall (default OFF).
        try:
            if (os.getenv("QUENTIN_MULTI_AGENT_MEMORY", "0") or "").strip().lower() in ("1", "true", "yes", "on"):
                from quentin.memory.fabric import MemoryFabric
                from quentin.memory.models import MemoryTier

                fabric = MemoryFabric(repo_root=repo_root)
                fabric.remember_atomic(
                    content=(
                        f"multi_agent_routing_decision chosen_model={chosen_model} domain={domain} "
                        f"task_meta={task_meta}"
                    ),
                    source="multi_agent",
                    tier=MemoryTier.STS,
                    domain=str(domain or "core"),
                    importance=0.2,
                    metadata={"decision": decision.to_dict(), "candidates": candidates, "task_meta": task_meta or {}},
                    kind="episodic",
                )
        except Exception:
            pass
        # Optional event bridge into SystemEventQueue (pluggable EventStore backend).
        try:
            events_on = (os.getenv("QUENTIN_MULTI_AGENT_EVENTS", "0") or "").strip().lower() in ("1", "true", "yes", "on")
            global_events_on = (os.getenv("QUENTIN_OUTCOME_EVENTS", "0") or "").strip().lower() in ("1", "true", "yes", "on")
            if events_on or global_events_on:
                from quentin.runtime.system_events import SystemEventQueue

                queue = SystemEventQueue(repo_root=repo_root)
                queue.enqueue_event(
                    session_id=session_id,
                    event_type="multi_agent_routing_decision",
                    payload={
                        "chosen_model": chosen_model,
                        "domain": str(domain or "core"),
                        "candidates": list(candidates or []),
                        "scores": dict(agg or {}),
                        "prompt_mode": str(prompt_mode),
                    },
                    source="multi_agent",
                )
        except Exception:
            pass

        return decision
