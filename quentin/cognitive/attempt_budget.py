from __future__ import annotations

import os
from dataclasses import asdict, dataclass
from typing import Any, Dict, Tuple


@dataclass
class AttemptBudgetState:
    initial_budget: float
    remaining_budget: float
    last_retry_cost: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def initialize_attempt_budget(*, max_loops: int) -> AttemptBudgetState:
    configured = float(os.getenv("QUENTIN_ATTEMPT_BUDGET", str(max_loops)) or max_loops)
    budget = max(1.0, configured)
    return AttemptBudgetState(initial_budget=budget, remaining_budget=budget, last_retry_cost=0.0)


def compute_retry_cost(*, attempt_evaluation: Dict[str, Any]) -> float:
    if not isinstance(attempt_evaluation, dict):
        return 1.0
    try:
        raw = attempt_evaluation.get("retry_cost")
        if raw is not None:
            return max(0.25, float(raw))
    except Exception:
        pass
    category = str(attempt_evaluation.get("category") or "").strip().lower()
    table = {
        "success": 0.25,
        "tool_execution_error": 1.0,
        "logic_path_error": 1.25,
        "plan_execution_misalignment": 1.75,
        "model_syntax_error": 1.0,
        "environment_timeout_error": 2.0,
        "system_error": 2.5,
        "mixed": 1.75,
    }
    return table.get(category, 1.0)


def consume_attempt_budget(
    *,
    state: AttemptBudgetState,
    attempt_evaluation: Dict[str, Any],
    step_result: str,
) -> Tuple[AttemptBudgetState, float]:
    # retry_same_attempt (compaction/thinking fallback) should not consume budget.
    if step_result == "retry":
        return state, 0.0
    cost = compute_retry_cost(attempt_evaluation=attempt_evaluation)
    remaining = max(0.0, float(state.remaining_budget) - float(cost))
    state.remaining_budget = remaining
    state.last_retry_cost = cost
    return state, cost
