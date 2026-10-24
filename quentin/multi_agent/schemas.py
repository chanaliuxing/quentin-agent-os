from __future__ import annotations

from enum import Enum
from typing import Dict, Any, List
from pydantic import BaseModel, Field


class AgentRole(str, Enum):
    SPEED = "speed"
    SAFETY = "safety"
    COST = "cost"
    DOMAIN_EXPERT = "domain_expert"


class RoleVote(BaseModel):
    """
    某个角色对某个模型的打分 / 投票。
    """
    role: AgentRole
    model_name: str
    score: float = 0.0
    reason: str = ""

    model_config = {"protected_namespaces": ()}


class RoutingDecision(BaseModel):
    """
    MultiAgentCoordinator 的总决策结果。
    """
    chosen_model: str
    votes: List[RoleVote] = Field(default_factory=list)
    meta: Dict[str, Any] = Field(default_factory=dict)

    model_config = {"protected_namespaces": ()}
