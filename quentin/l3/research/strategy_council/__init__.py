"""
Strategy Council Module

Multi-LLM strategy generation, review, and synthesis with hedge planning.
"""

from quentin.l3.research.strategy_council.council import (
    StrategyProposal,
    HedgePlan,
    ReviewFeedback,
    FinalPlan,
    PaperResult,
    generate_proposals,
    cross_review,
    synthesize_plan,
    run_paper_plan,
    run_council,
)

from quentin.l3.research.strategy_council.plan_logger import (
    log_plan_vs_outcome,
    load_recent_plan_outcomes,
)

__all__ = [
    "StrategyProposal",
    "HedgePlan",
    "ReviewFeedback",
    "FinalPlan",
    "PaperResult",
    "generate_proposals",
    "cross_review",
    "synthesize_plan",
    "run_paper_plan",
    "run_council",
    "log_plan_vs_outcome",
    "load_recent_plan_outcomes",
]
