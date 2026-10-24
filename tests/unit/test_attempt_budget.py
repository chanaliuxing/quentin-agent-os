from __future__ import annotations

from quentin.cognitive.attempt_budget import (
    AttemptBudgetState,
    compute_retry_cost,
    consume_attempt_budget,
)


def test_compute_retry_cost_prefers_explicit_field() -> None:
    assert compute_retry_cost(attempt_evaluation={"retry_cost": 1.75}) == 1.75


def test_compute_retry_cost_timeout_higher_than_model_syntax() -> None:
    timeout_cost = compute_retry_cost(attempt_evaluation={"category": "environment_timeout_error"})
    syntax_cost = compute_retry_cost(attempt_evaluation={"category": "model_syntax_error"})
    assert timeout_cost > syntax_cost


def test_compute_retry_cost_misalignment_higher_than_tool_error() -> None:
    misalign_cost = compute_retry_cost(attempt_evaluation={"category": "plan_execution_misalignment"})
    tool_cost = compute_retry_cost(attempt_evaluation={"category": "tool_execution_error"})
    assert misalign_cost > tool_cost


def test_consume_attempt_budget_skips_retry_same_attempt() -> None:
    state = AttemptBudgetState(initial_budget=5.0, remaining_budget=5.0)
    next_state, consumed = consume_attempt_budget(
        state=state,
        attempt_evaluation={"category": "environment_timeout_error"},
        step_result="retry",
    )
    assert next_state.remaining_budget == 5.0
    assert consumed == 0.0


def test_consume_attempt_budget_decrements_for_non_retry() -> None:
    state = AttemptBudgetState(initial_budget=5.0, remaining_budget=5.0)
    next_state, consumed = consume_attempt_budget(
        state=state,
        attempt_evaluation={"category": "environment_timeout_error"},
        step_result="continue",
    )
    assert consumed >= 2.0
    assert next_state.remaining_budget <= 3.0
