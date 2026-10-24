"""
Meta-experiment system for comparing evolution strategy effectiveness.

This module allows the self-programming system to run experiments comparing
different strategy configurations and automatically adjust strategy weights
based on empirical results.
"""
from __future__ import annotations
from quentin.utils.time import now_iso, now_utc

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
from pathlib import Path

from meta_agent.self_programming.strategy import EvolutionStrategyManager, StrategyType
from meta_agent.self_programming.metrics_store import MetricsStoreProtocol, RunRecord

logger = logging.getLogger(__name__)


@dataclass
class StrategyVariant:
    """A specific configuration of strategy weights to test."""
    variant_id: str
    name: str
    weights: Dict[StrategyType, float]
    description: str = ""


@dataclass
class ExperimentRun:
    """Results from running a strategy variant."""
    variant_id: str
    timestamp: datetime
    tasks_generated: int
    tasks_successful: int
    tasks_failed: int
    avg_complexity_reduction: float
    avg_test_coverage_improvement: float
    total_cost_usd: float = 0.0
    total_tokens: int = 0


@dataclass
class ExperimentResult:
    """Aggregated results from a meta-experiment."""
    experiment_id: str
    started_at: datetime
    finished_at: Optional[datetime]
    variants: List[StrategyVariant]
    runs: List[ExperimentRun] = field(default_factory=list)
    winner: Optional[str] = None
    confidence: float = 0.0


class MetaExperimentOrchestrator:
    """
    Orchestrates experiments comparing different evolution strategies.

    This allows the system to empirically determine which strategy mix
    is most effective and automatically adjust weights.
    """

    def __init__(
        self,
        metrics_store: MetricsStoreProtocol,
        repo_root: str = ".",
    ):
        self.metrics_store = metrics_store
        self.repo_root = Path(repo_root)

    def create_experiment(
        self,
        experiment_id: str,
        variants: List[StrategyVariant],
    ) -> ExperimentResult:
        """
        Create a new meta-experiment comparing strategy variants.

        Args:
            experiment_id: Unique identifier for the experiment
            variants: List of strategy configurations to test

        Returns:
            ExperimentResult object to track progress
        """
        logger.info("Creating meta-experiment %s with %d variants", experiment_id, len(variants))

        return ExperimentResult(
            experiment_id=experiment_id,
            started_at=now_utc(),
            finished_at=None,
            variants=variants,
            runs=[],
        )

    def run_variant(
        self,
        variant: StrategyVariant,
        task_limit: int = 10,
        time_window_hours: int = 24,
    ) -> ExperimentRun:
        """
        Run a single strategy variant and collect metrics.

        Args:
            variant: Strategy configuration to test
            task_limit: Maximum number of tasks to generate
            time_window_hours: Look back window for metrics analysis

        Returns:
            ExperimentRun with results
        """
        logger.info("Running variant %s: %s", variant.variant_id, variant.name)

        # Create strategy manager with this variant's weights
        strategy_mgr = EvolutionStrategyManager(
            metrics_store=self.metrics_store,
            repo_root=str(self.repo_root),
            strategy_weights=variant.weights,
        )

        # Generate tasks using this strategy
        tasks = strategy_mgr.generate_tasks(limit=task_limit)
        logger.info("Generated %d tasks for variant %s", len(tasks), variant.variant_id)

        # Analyze recent runs to get success metrics
        # Note: JsonlMetricsStore doesn't have query_runs, so we'll get by status
        approved_runs = self.metrics_store.get_runs_by_status("approved", limit=100)
        failed_runs = self.metrics_store.get_runs_by_status("error", limit=100)
        test_fail_runs = self.metrics_store.get_runs_by_status("test_fail", limit=100)

        # Filter by time window
        cutoff = now_utc() - timedelta(hours=time_window_hours)
        recent_runs = [
            r for r in (approved_runs + failed_runs + test_fail_runs)
            if r.get("timestamp", datetime.min) > cutoff
        ]

        # Calculate metrics
        tasks_successful = len([r for r in recent_runs if r.get("status") == "approved"])
        tasks_failed = len([r for r in recent_runs if r.get("status") in ("error", "test_fail")])

        # Calculate complexity and coverage improvements
        complexity_improvements = []
        coverage_improvements = []

        for run in recent_runs:
            metrics = run.get("metrics", {})
            if "complexity_change" in metrics:
                complexity_improvements.append(metrics["complexity_change"])
            if "coverage_change" in metrics:
                coverage_improvements.append(metrics["coverage_change"])

        avg_complexity = (
            sum(complexity_improvements) / len(complexity_improvements)
            if complexity_improvements
            else 0.0
        )
        avg_coverage = (
            sum(coverage_improvements) / len(coverage_improvements)
            if coverage_improvements
            else 0.0
        )

        return ExperimentRun(
            variant_id=variant.variant_id,
            timestamp=now_utc(),
            tasks_generated=len(tasks),
            tasks_successful=tasks_successful,
            tasks_failed=tasks_failed,
            avg_complexity_reduction=avg_complexity,
            avg_test_coverage_improvement=avg_coverage,
        )

    def run_experiment(
        self,
        experiment: ExperimentResult,
        task_limit_per_variant: int = 10,
        time_window_hours: int = 24,
    ) -> ExperimentResult:
        """
        Run all variants in an experiment and collect results.

        Args:
            experiment: ExperimentResult to populate with runs
            task_limit_per_variant: Tasks to generate per variant
            time_window_hours: Analysis window

        Returns:
            Updated ExperimentResult with all runs
        """
        logger.info("Running experiment %s with %d variants", experiment.experiment_id, len(experiment.variants))

        for variant in experiment.variants:
            try:
                run = self.run_variant(
                    variant,
                    task_limit=task_limit_per_variant,
                    time_window_hours=time_window_hours,
                )
                experiment.runs.append(run)
            except Exception as e:
                logger.error("Failed to run variant %s: %s", variant.variant_id, e)

        experiment.finished_at = now_utc()
        return experiment

    def analyze_results(
        self,
        experiment: ExperimentResult,
        primary_metric: str = "success_rate",
        min_confidence: float = 0.7,
    ) -> Tuple[Optional[StrategyVariant], float]:
        """
        Analyze experiment results and determine winning strategy.

        Args:
            experiment: Completed experiment
            primary_metric: Metric to optimize (success_rate, complexity_reduction, coverage_improvement)
            min_confidence: Minimum confidence threshold

        Returns:
            (winner_variant, confidence) tuple
        """
        if not experiment.runs:
            logger.warning("No runs to analyze")
            return None, 0.0

        # Calculate scores for each variant
        variant_scores: Dict[str, float] = {}

        for run in experiment.runs:
            if primary_metric == "success_rate":
                total_tasks = run.tasks_successful + run.tasks_failed
                score = run.tasks_successful / total_tasks if total_tasks > 0 else 0.0
            elif primary_metric == "complexity_reduction":
                # Higher reduction is better (positive value)
                score = max(0, run.avg_complexity_reduction)
            elif primary_metric == "coverage_improvement":
                score = max(0, run.avg_test_coverage_improvement)
            else:
                score = 0.0

            variant_scores[run.variant_id] = score

        # Find winner
        if not variant_scores:
            return None, 0.0

        winner_id = max(variant_scores, key=variant_scores.get)
        winner_score = variant_scores[winner_id]

        # Calculate confidence based on margin from second place
        scores_sorted = sorted(variant_scores.values(), reverse=True)
        if len(scores_sorted) >= 2:
            margin = scores_sorted[0] - scores_sorted[1]
            confidence = min(1.0, 0.5 + margin)  # Simple confidence metric
        else:
            confidence = 0.5

        # Find winner variant object
        winner_variant = next((v for v in experiment.variants if v.variant_id == winner_id), None)

        experiment.winner = winner_id
        experiment.confidence = confidence

        logger.info(
            "Experiment %s winner: %s (score=%.3f, confidence=%.3f)",
            experiment.experiment_id,
            winner_id,
            winner_score,
            confidence,
        )

        return winner_variant, confidence

    def auto_adjust_weights(
        self,
        current_weights: Dict[StrategyType, float],
        experiment: ExperimentResult,
        learning_rate: float = 0.1,
    ) -> Dict[StrategyType, float]:
        """
        Automatically adjust strategy weights based on experiment results.

        Args:
            current_weights: Current strategy weights
            experiment: Completed experiment with winner
            learning_rate: How much to adjust (0.0-1.0)

        Returns:
            New adjusted weights
        """
        if not experiment.winner:
            logger.warning("No winner to learn from")
            return current_weights

        winner_variant = next((v for v in experiment.variants if v.variant_id == experiment.winner), None)
        if not winner_variant:
            return current_weights

        # Interpolate between current and winner weights
        new_weights = {}
        for strategy_type in current_weights:
            current = current_weights[strategy_type]
            target = winner_variant.weights.get(strategy_type, current)
            new_weights[strategy_type] = current + learning_rate * (target - current)

        # Normalize to sum to 1.0
        total = sum(new_weights.values())
        if total > 0:
            new_weights = {k: v / total for k, v in new_weights.items()}

        logger.info("Adjusted weights: %s -> %s", current_weights, new_weights)

        return new_weights

    def save_experiment(self, experiment: ExperimentResult, output_path: Optional[Path] = None) -> None:
        """
        Save experiment results to disk for analysis.

        Args:
            experiment: Experiment to save
            output_path: Optional custom path (defaults to data/experiments/<id>.json)
        """
        import json

        if output_path is None:
            output_path = self.repo_root / "data" / "experiments" / f"{experiment.experiment_id}.json"

        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Convert to dict
        data = {
            "experiment_id": experiment.experiment_id,
            "started_at": experiment.started_at.isoformat(),
            "finished_at": experiment.finished_at.isoformat() if experiment.finished_at else None,
            "winner": experiment.winner,
            "confidence": experiment.confidence,
            "variants": [
                {
                    "variant_id": v.variant_id,
                    "name": v.name,
                    "weights": v.weights,
                    "description": v.description,
                }
                for v in experiment.variants
            ],
            "runs": [
                {
                    "variant_id": r.variant_id,
                    "timestamp": r.timestamp.isoformat(),
                    "tasks_generated": r.tasks_generated,
                    "tasks_successful": r.tasks_successful,
                    "tasks_failed": r.tasks_failed,
                    "avg_complexity_reduction": r.avg_complexity_reduction,
                    "avg_test_coverage_improvement": r.avg_test_coverage_improvement,
                }
                for r in experiment.runs
            ],
        }

        with output_path.open("w") as f:
            json.dump(data, f, indent=2)

        logger.info("Saved experiment to %s", output_path)


def create_default_variants() -> List[StrategyVariant]:
    """Create a default set of strategy variants for experimentation."""
    return [
        StrategyVariant(
            variant_id="baseline",
            name="Balanced Mix",
            weights={
                "retry_failed": 0.6,
                "find_untested_code": 0.25,
                "find_complex_code": 0.15,
            },
            description="Default balanced strategy mix",
        ),
        StrategyVariant(
            variant_id="test_focused",
            name="Test Coverage Focused",
            weights={
                "retry_failed": 0.3,
                "find_untested_code": 0.6,
                "find_complex_code": 0.1,
            },
            description="Prioritize improving test coverage",
        ),
        StrategyVariant(
            variant_id="quality_focused",
            name="Code Quality Focused",
            weights={
                "retry_failed": 0.3,
                "find_untested_code": 0.1,
                "find_complex_code": 0.6,
            },
            description="Prioritize reducing complexity",
        ),
        StrategyVariant(
            variant_id="reliability_focused",
            name="Reliability Focused",
            weights={
                "retry_failed": 0.8,
                "find_untested_code": 0.1,
                "find_complex_code": 0.1,
            },
            description="Focus on fixing failures",
        ),
    ]
