from __future__ import annotations
from dataclasses import dataclass
from typing import Optional

@dataclass
class TokenBudgetConfig:
    max_tokens_per_cycle: int = 1_000_000
    deduct_percentage_on_fail: float = 0.1

class TokenBudgetManager:
    def __init__(self, budget_manager=None, config: Optional[TokenBudgetConfig] = None) -> None:
        self.budget_manager = budget_manager # Assuming BudgetManager is passed in
        self.config = config or TokenBudgetConfig()
        self._current_cycle_tokens_spent = 0

    def reset_cycle(self) -> None:
        self._current_cycle_tokens_spent = 0

    def can_run(self, estimated_tokens: int) -> bool:
        if self._current_cycle_tokens_spent + estimated_tokens > self.config.max_tokens_per_cycle:
            return False
        # Assuming BudgetManager also has a can_afford method based on actual USD cost
        # For now, just check token budget
        return True

    def consume(self, actual_tokens: int) -> bool:
        self._current_cycle_tokens_spent += actual_tokens
        # Assuming a simple token to USD conversion for BudgetManager
        # This part will be mocked more thoroughly in integration tests
        usd_cost = actual_tokens / 1000000.0 # Example: 1 token = 0.000001 USD
        if self.budget_manager:
            return self.budget_manager.deduct_budget(usd_cost)
        return True # Assume success if no budget manager is attached
