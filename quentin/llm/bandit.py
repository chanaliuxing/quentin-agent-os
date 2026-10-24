from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Optional
import random


@dataclass
class BanditArm:
    arm_id: str
    meta: Dict[str, Any] = None

    def to_dict(self) -> Dict[str, Any]:
        return {"arm_id": self.arm_id, "meta": dict(self.meta or {})}


@dataclass
class BanditDecision:
    arm_id: str
    reason: str
    score: float = 0.0
    meta: Dict[str, Any] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class BanditPolicy:
    """
    Minimal interface for learned routing policies.
    """

    def choose(self, *, arms: List[BanditArm], context: Optional[Dict[str, Any]] = None) -> BanditDecision:  # pragma: no cover
        raise RuntimeError("BanditPolicy is an interface; use EpsilonGreedyBandit or a learned policy.")


class EpsilonGreedyBandit(BanditPolicy):
    """
    Minimal bandit policy:
    - Exploit: pick the arm with highest `context['scores'][arm_id]` if provided.
    - Explore: random arm with probability epsilon.
    """

    def __init__(self, *, epsilon: float = 0.1) -> None:
        self.epsilon = max(0.0, min(1.0, float(epsilon)))

    def choose(self, *, arms: List[BanditArm], context: Optional[Dict[str, Any]] = None) -> BanditDecision:
        if not arms:
            return BanditDecision(arm_id="", reason="no_arms", score=0.0, meta={})

        if random.random() < self.epsilon:
            arm = random.choice(arms)
            return BanditDecision(arm_id=arm.arm_id, reason="explore", score=0.0, meta={"epsilon": self.epsilon})

        scores = (context or {}).get("scores") or {}
        best = None
        best_score = float("-inf")
        for a in arms:
            s = float(scores.get(a.arm_id, 0.0)) if isinstance(scores, dict) else 0.0
            if s > best_score:
                best = a
                best_score = s
        chosen = best or arms[0]
        return BanditDecision(arm_id=chosen.arm_id, reason="exploit", score=float(best_score), meta={"epsilon": self.epsilon})
