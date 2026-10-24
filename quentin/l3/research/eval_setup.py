"""
Eval Harness Setup Utilities

Helpers to wire real evaluators into the eval harness.
"""

from typing import Dict, Any, Optional
from quentin.l3.research.eval_harness import EvalHarness, EvalCase
from quentin.l3.research.evaluators import get_evaluator, EVALUATOR_REGISTRY
from quentin.kernel.schemas import ExperimentVariant


def setup_default_evaluators(harness: EvalHarness) -> None:
    """
    Register all default evaluators with the harness.

    Args:
        harness: EvalHarness instance to register evaluators with
    """
    # Register keyword evaluator for general text evaluation
    keyword_eval = get_evaluator("keyword")
    harness.register_evaluator(
        "text_generation",
        lambda case, variant: _evaluator_to_dict(keyword_eval, case, variant)
    )

    # Register model output evaluator for LLM outputs
    model_eval = get_evaluator("model_output")
    harness.register_evaluator(
        "model_output",
        lambda case, variant: _evaluator_to_dict(model_eval, case, variant)
    )

    # Register strategy backtest evaluator
    strategy_eval = get_evaluator("strategy_backtest")
    harness.register_evaluator(
        "strategy",
        lambda case, variant: _evaluator_to_dict(strategy_eval, case, variant)
    )

    # Register code quality evaluator
    code_eval = get_evaluator("code_quality")
    harness.register_evaluator(
        "code_generation",
        lambda case, variant: _evaluator_to_dict(code_eval, case, variant)
    )

    # Also register as default fallback
    harness.register_evaluator(
        "default",
        lambda case, variant: _evaluator_to_dict(keyword_eval, case, variant)
    )


def register_custom_evaluator(
    harness: EvalHarness,
    target_type: str,
    evaluator_type: str,
    **evaluator_kwargs
) -> None:
    """
    Register a custom evaluator configuration.

    Args:
        harness: EvalHarness instance
        target_type: Target type to register for
        evaluator_type: Type of evaluator from registry
        **evaluator_kwargs: Additional arguments for evaluator constructor
    """
    evaluator = get_evaluator(evaluator_type, **evaluator_kwargs)
    harness.register_evaluator(
        target_type,
        lambda case, variant: _evaluator_to_dict(evaluator, case, variant)
    )


def _evaluator_to_dict(evaluator, case: EvalCase, variant: ExperimentVariant) -> Dict[str, Any]:
    """
    Convert evaluator result to dict format expected by eval harness.

    Args:
        evaluator: Evaluator instance
        case: Evaluation case
        variant: Experiment variant

    Returns:
        Dict with success, latency_ms, cost_tokens, raw_output, raw_metrics, notes
    """
    result = evaluator.evaluate(case, variant)

    return {
        "success": result.success,
        "latency_ms": result.latency_ms,
        "cost_tokens": result.cost_tokens,
        "raw_output": result.raw_output,
        "raw_metrics": result.raw_metrics,
        "notes": result.notes,
    }


def get_evaluator_info() -> Dict[str, str]:
    """
    Get information about available evaluators.

    Returns:
        Dict mapping evaluator types to descriptions
    """
    return {
        "keyword": "Keyword-based text evaluation (default)",
        "model_output": "LLM output quality evaluation",
        "strategy_backtest": "Trading strategy backtest evaluation",
        "code_quality": "Generated code quality evaluation",
    }


def print_evaluator_info() -> None:
    """Print information about available evaluators."""
    print("\nAvailable Evaluators:")
    print("=" * 60)

    for eval_type, description in get_evaluator_info().items():
        print(f"  • {eval_type:20s} - {description}")

    print("\nUsage:")
    print("  from quentin.l3.research.eval_setup import setup_default_evaluators")
    print("  from quentin.l3.research.eval_harness import EvalHarness")
    print("")
    print("  harness = EvalHarness(...)")
    print("  setup_default_evaluators(harness)")
    print("")
