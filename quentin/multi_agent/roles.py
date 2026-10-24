from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional

from quentin.multi_agent.schemas import AgentRole, RoleVote
from quentin.config.settings import Settings


class BaseAgentRole(ABC):
    """
    多智能体协调中“角色”的基类。
    """
    def __init__(self, role: AgentRole, weight: float = 1.0):
        self.role = role
        self.weight = weight

    @abstractmethod
    def vote(
        self,
        model_stats: Dict[str, Dict[str, Any]],
        candidates: List[str],
        task_meta: Dict[str, Any],
        settings: Settings,
    ) -> List[RoleVote]:
        """
        每个角色根据自己的标准，为候选模型投票。
        """
        pass


class SpeedAgent(BaseAgentRole):
    def __init__(self, weight: float = 1.0):
        super().__init__(AgentRole.SPEED, weight)

    def vote(
        self,
        model_stats: Dict[str, Dict[str, Any]],
        candidates: List[str],
        task_meta: Dict[str, Any],
        settings: Settings,
    ) -> List[RoleVote]:
        votes: List[RoleVote] = []
        for m in candidates:
            s = model_stats.get(m, {})
            lat = s.get("avg_latency_sec", 0.0) or 0.0
            score = 1.0 / lat if lat > 0 else 0.0
            votes.append(
                RoleVote(
                    role=self.role,
                    model_name=m,
                    score=score,
                    reason=f"avg_latency_sec={lat}",
                )
            )
        return votes


class CostAgent(BaseAgentRole):
    def __init__(self, weight: float = 1.0):
        super().__init__(AgentRole.COST, weight)

    def vote(
        self,
        model_stats: Dict[str, Dict[str, Any]],
        candidates: List[str],
        task_meta: Dict[str, Any],
        settings: Settings,
    ) -> List[RoleVote]:
        votes: List[RoleVote] = []
        for m in candidates:
            s = model_stats.get(m, {})
            cost = s.get("avg_cost")
            score = 1.0 / cost if cost and cost > 0 else 0.0
            votes.append(
                RoleVote(
                    role=self.role,
                    model_name=m,
                    score=score,
                    reason=f"avg_cost={cost}",
                )
            )
        return votes


class SafetyAgent(BaseAgentRole):
    def __init__(self, weight: float = 1.0):
        super().__init__(AgentRole.SAFETY, weight)

    def vote(
        self,
        model_stats: Dict[str, Dict[str, Any]],
        candidates: List[str],
        task_meta: Dict[str, Any],
        settings: Settings,
    ) -> List[RoleVote]:
        whitelist = set(getattr(settings, "safety_model_whitelist", []) or [])
        blacklist = set(getattr(settings, "safety_model_blacklist", []) or [])

        votes: List[RoleVote] = []
        for m in candidates:
            score = 0.0
            reason = "neutral"
            if blacklist and m in blacklist:
                score = -1.0
                reason = "blacklisted"
            elif whitelist and m in whitelist:
                score = 1.0
                reason = "whitelisted"
            
            votes.append(
                RoleVote(
                    role=self.role,
                    model_name=m,
                    score=score,
                    reason=reason,
                )
            )
        return votes


class DomainExpertAgent(BaseAgentRole):
    def __init__(self, weight: float = 1.0):
        super().__init__(AgentRole.DOMAIN_EXPERT, weight)

    def vote(
        self,
        model_stats: Dict[str, Dict[str, Any]],
        candidates: List[str],
        task_meta: Dict[str, Any],
        settings: Settings,
    ) -> List[RoleVote]:
        domain = task_meta.get("domain")
        prefs: Dict[str, List[str]] = getattr(settings, "domain_model_preferences", {}) or {}
        preferred = prefs.get(domain or "", [])

        votes: List[RoleVote] = []
        for m in candidates:
            score = 1.0 if preferred and m in preferred else 0.0
            reason = "preferred_for_domain" if score > 0 else "neutral"
            votes.append(
                RoleVote(
                    role=self.role,
                    model_name=m,
                    score=score,
                    reason=reason,
                )
            )
        return votes
