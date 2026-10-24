from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, Optional
import json
import time
import os


@dataclass
class BudgetState:
    """
    Minimal USD budget state for self-evolution actions.

    This is intentionally small and schema-stable: tests and observability depend on it.
    """

    usd_remaining: float = 0.0
    updated_at: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, raw: Dict[str, Any]) -> "BudgetState":
        if not isinstance(raw, dict):
            return cls()
        try:
            usd_remaining = float(raw.get("usd_remaining", 0.0))
        except Exception:
            usd_remaining = 0.0
        try:
            updated_at = float(raw.get("updated_at", 0.0))
        except Exception:
            updated_at = 0.0
        return cls(usd_remaining=usd_remaining, updated_at=updated_at)


class BudgetManager:
    """
    File-backed budget manager used by SelfEvoActionScheduler.

    The interface is intentionally tiny:
    - can_afford(usd_cost) -> bool
    - deduct_budget(usd_cost) -> None
    - get_current_budget() -> float
    """

    def __init__(self, *, path: str | Path = "data/evolution/budget.json", initial_usd: float = 0.0) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists() and initial_usd:
            self._save(BudgetState(usd_remaining=float(initial_usd), updated_at=time.time()))

    def _load(self) -> BudgetState:
        if not self.path.exists():
            return BudgetState(usd_remaining=0.0, updated_at=0.0)
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            return BudgetState(usd_remaining=0.0, updated_at=0.0)
        return BudgetState.from_dict(raw)

    def _save(self, state: BudgetState) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text(json.dumps(state.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self.path)

    def get_current_budget(self) -> float:
        return float(self._load().usd_remaining)

    def can_afford(self, usd_cost: float) -> bool:
        state = self._load()
        return float(state.usd_remaining) >= float(usd_cost)

    def deduct_budget(self, usd_cost: float) -> None:
        state = self._load()
        state.usd_remaining = float(state.usd_remaining) - float(usd_cost)
        state.updated_at = time.time()
        self._save(state)


def default_budget_manager() -> BudgetManager:
    """
    Conservative default: zero budget unless explicitly configured by the operator.
    """

    initial = float((os.environ.get("META_AGENT_USD_BUDGET") or "0") or 0)
    return BudgetManager(initial_usd=initial)
