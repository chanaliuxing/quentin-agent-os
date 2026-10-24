from __future__ import annotations
from quentin.utils.time import now_iso, now_utc

from dataclasses import dataclass, field, asdict
from typing import Any, Callable, Dict, List, Optional, Literal, Tuple
import datetime as dt
import time
import uuid

from meta_agent.evolution.budget import BudgetManager
from meta_agent.evolution.token_budget import TokenBudgetManager


ActionKind = Literal[
    "blueprint_update",
    "patch_experiment",
    "research_experiment",
    "web_research",
    "code_refactor",
    "other_note",
]


@dataclass(order=True)
class SelfEvoAction:
    sort_index: float = field(init=False, repr=False)
    priority: int
    created_at: str
    id: str
    kind: ActionKind
    estimated_tokens: int
    payload: Dict[str, Any]
    section_id: Optional[str] = None

    def __post_init__(self) -> None:
        try:
            ts = dt.datetime.fromisoformat(self.created_at.replace("Z", "+00:00")).timestamp()
        except Exception:
            ts = time.time()
        self.sort_index = (-int(self.priority or 0), ts)

    @staticmethod
    def new(
        *,
        kind: ActionKind,
        priority: int,
        estimated_tokens: int,
        payload: Dict[str, Any],
        section_id: Optional[str] = None,
    ) -> "SelfEvoAction":
        now = now_iso()
        return SelfEvoAction(
            id=f"evo-{uuid.uuid4().hex[:8]}",
            kind=kind,
            priority=int(priority),
            estimated_tokens=int(estimated_tokens),
            payload=payload,
            created_at=now,
            section_id=section_id,
        )

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class CooldownRegistry:
    def __init__(self, cooldown_seconds: int = 600) -> None:
        self.cooldown_seconds = int(cooldown_seconds)
        self.last_run: Dict[Tuple[str, ActionKind], float] = {}

    def is_cooldown(self, section_id: Optional[str], kind: ActionKind) -> bool:
        key = (section_id or "", kind)
        ts = self.last_run.get(key)
        if ts is None:
            return False
        return (time.time() - ts) < self.cooldown_seconds

    def mark_run(self, section_id: Optional[str], kind: ActionKind) -> None:
        key = (section_id or "", kind)
        self.last_run[key] = time.time()


class SelfEvoActionScheduler:
    """
    Select a subset of candidate actions under:
    - cooldown limits (avoid thrashing the same section)
    - token budget limits (cheap first)
    - optional USD budget (via BudgetManager)
    """

    def __init__(
        self,
        *,
        budget: Optional[BudgetManager] = None,
        cooldown_registry: Optional[CooldownRegistry] = None,
        handlers: Optional[Dict[str, Callable[[SelfEvoAction], Dict[str, Any]]]] = None,
    ) -> None:
        self.usd_budget = budget
        self.token_budget = TokenBudgetManager(budget_manager=budget)
        self.cooldown = cooldown_registry or CooldownRegistry()
        self.handlers = handlers or {}

    def schedule(self, candidate_actions: List[Dict[str, Any]]) -> List[SelfEvoAction]:
        self.token_budget.reset_cycle()

        acts: List[SelfEvoAction] = []
        for i, a in enumerate(candidate_actions or []):
            kind = a.get("kind") or "other_note"
            if kind not in (
                "blueprint_update",
                "patch_experiment",
                "research_experiment",
                "web_research",
                "code_refactor",
                "other_note",
            ):
                kind = "other_note"
            pri = int(a.get("priority", 5) or 5)
            payload = a.get("payload", {}) or {}
            section_id = a.get("section_id") or payload.get("section_id")
            est_tokens = int(a.get("estimated_tokens") or 3000)
            acts.append(
                SelfEvoAction.new(
                    kind=kind,  # type: ignore[arg-type]
                    priority=pri,
                    estimated_tokens=est_tokens,
                    payload=payload,
                    section_id=section_id,
                )
            )

        acts.sort()  # uses sort_index: higher priority first, older first

        selected: List[SelfEvoAction] = []
        for act in acts:
            if self.cooldown.is_cooldown(act.section_id, act.kind):
                continue
            if not self.token_budget.can_run(act.estimated_tokens):
                continue

            # If an external USD budget is present, charge a tiny amount proportional to tokens.
            if self.usd_budget is not None:
                usd_cost = act.estimated_tokens / 1_000_000.0
                if hasattr(self.usd_budget, "can_afford") and not self.usd_budget.can_afford(usd_cost):
                    continue
                if hasattr(self.usd_budget, "deduct_budget"):
                    self.usd_budget.deduct_budget(usd_cost)

            self.token_budget.consume(act.estimated_tokens)
            self.cooldown.mark_run(act.section_id, act.kind)
            selected.append(act)

        return selected


class ActionBuilder:
    @staticmethod
    def from_research_plan(plan: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Normalize different plan shapes into scheduler inputs:
        - v1: {"actions": [{"kind", "priority", "estimated_tokens", "payload"}]}
        - v2: MetaResearchAgent dataclasses (converted by orchestrator)
        """

        acts_raw = plan.get("actions") or []
        out: List[Dict[str, Any]] = []
        for a in acts_raw:
            if not isinstance(a, dict):
                continue
            out.append(
                {
                    "kind": a.get("kind") or "other_note",
                    "priority": int(a.get("priority", 5) or 5),
                    "estimated_tokens": int(a.get("estimated_tokens") or 3000),
                    "payload": a.get("payload") or {},
                    "section_id": a.get("section_id"),
                }
            )
        return out

