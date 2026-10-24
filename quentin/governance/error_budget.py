from __future__ import annotations
import logging
from dataclasses import dataclass, field
from typing import Dict, Any, Optional
from quentin.governance.slo_registry import SLORegistry

logger = logging.getLogger(__name__)

@dataclass
class ErrorBudget:
    slo_name: str
    total_budget: float # e.g., 0.001 if SLO is 0.999
    remaining_budget: float
    is_exhausted: bool = False

class ErrorBudgetController:
    """
    P5-A: Error Budget Controller
    Triggers degradation mode when budget is exhausted.
    """
    def __init__(self, registry: Optional[SLORegistry] = None) -> None:
        self.registry = registry or SLORegistry()
        self.budgets: Dict[str, ErrorBudget] = {}
        self._initialize_budgets()

    def _initialize_budgets(self) -> None:
        for name, slo in self.registry.list_all().items():
            budget_val = 1.0 - slo.target if slo.target <= 1.0 else slo.target * 0.1 # heuristic for non-percentage
            self.budgets[name] = ErrorBudget(
                slo_name=name,
                total_budget=budget_val,
                remaining_budget=budget_val
            )

    def report_error(self, slo_name: str, impact: float) -> None:
        """
        Consume error budget.
        """
        if slo_name not in self.budgets:
            return
        
        budget = self.budgets[slo_name]
        budget.remaining_budget -= impact
        if budget.remaining_budget <= 0:
            budget.is_exhausted = True
            logger.warning("Error budget for SLO '%s' EXHAUSTED. Triggering degradation.", slo_name)

    def is_degradation_required(self) -> bool:
        """
        Check if any critical budget is exhausted.
        """
        return any(b.is_exhausted for b in self.budgets.values())

    def get_degradation_mode(self) -> Dict[str, Any]:
        """
        Returns recommended settings for degradation.
        """
        if not self.is_degradation_required():
            return {"mode": "normal"}
        
        return {
            "mode": "degrade",
            "disable_high_risk_evolution": True,
            "concurrency_limit_multiplier": 0.5,
            "prefer_conservative_models": True
        }
