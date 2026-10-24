"""
Demo script for multi-strategy EvolutionStrategyManager (Phase 2).

This script demonstrates the new proactive improvement strategies:
1. retry_failed: Reactive - retry test failures
2. find_untested_code: Proactive - add tests for low coverage modules
3. find_complex_code: Proactive - refactor high-complexity functions

Usage:
    python scripts/demo_multi_strategy.py [--limit 10] [--dry-run]
"""
from __future__ import annotations

import argparse
import logging
from pathlib import Path

from meta_agent.self_programming.strategy import EvolutionStrategyManager
from meta_agent.self_programming.metrics_store import JsonlMetricsStore

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Demo multi-strategy evolution manager")
    parser.add_argument(
        "--limit",
        type=int,
        default=5,
        help="Max tasks to generate (default: 5)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Generate tasks but don't execute them",
    )
    parser.add_argument(
        "--weights",
        type=str,
        default="0.6,0.25,0.15",
        help="Strategy weights (retry,untested,complex), e.g., '0.5,0.3,0.2'",
    )
    parser.add_argument(
        "--coverage-threshold",
        type=float,
        default=0.80,
        help="Coverage threshold for find_untested_code (default: 0.80)",
    )
    parser.add_argument(
        "--complexity-threshold",
        type=int,
        default=10,
        help="Complexity threshold for find_complex_code (default: 10)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    repo_root = Path(__file__).resolve().parents[1]

    # Parse weights
    weight_values = [float(w) for w in args.weights.split(",")]
    if len(weight_values) != 3:
        logger.error("--weights must have 3 values: retry,untested,complex")
        return

    strategy_weights = {
        "retry_failed": weight_values[0],
        "find_untested_code": weight_values[1],
        "find_complex_code": weight_values[2],
    }

    logger.info("=" * 60)
    logger.info("Multi-Strategy Evolution Manager Demo")
    logger.info("=" * 60)
    logger.info("Configuration:")
    logger.info("  Task limit: %d", args.limit)
    logger.info("  Strategy weights:")
    logger.info("    - retry_failed:      %.0f%%", strategy_weights["retry_failed"] * 100)
    logger.info("    - find_untested_code: %.0f%%", strategy_weights["find_untested_code"] * 100)
    logger.info("    - find_complex_code:  %.0f%%", strategy_weights["find_complex_code"] * 100)
    logger.info("  Coverage threshold: %.0f%%", args.coverage_threshold * 100)
    logger.info("  Complexity threshold: %d", args.complexity_threshold)
    logger.info("  Mode: %s", "DRY RUN" if args.dry_run else "EXECUTE")
    logger.info("=" * 60)

    # Initialize components
    metrics_store = JsonlMetricsStore(repo_root=repo_root)
    manager = EvolutionStrategyManager(
        metrics_store=metrics_store,
        repo_root=str(repo_root),
        strategy_weights=strategy_weights,
        coverage_threshold=args.coverage_threshold,
        complexity_threshold=args.complexity_threshold,
    )

    # Generate tasks
    logger.info("\nGenerating tasks...")
    tasks = manager.generate_tasks(limit=args.limit)

    if not tasks:
        logger.info("No tasks generated.")
        return

    logger.info("Generated %d tasks:\n", len(tasks))

    # Group tasks by strategy
    by_strategy: dict[str, list] = {
        "retry_failed": [],
        "find_untested_code": [],
        "find_complex_code": [],
    }

    for task in tasks:
        if "retry_of" in task.task_id:
            by_strategy["retry_failed"].append(task)
        elif "add_tests" in task.task_id:
            by_strategy["find_untested_code"].append(task)
        elif "refactor_complex" in task.task_id:
            by_strategy["find_complex_code"].append(task)

    # Print summary by strategy
    for strategy, strategy_tasks in by_strategy.items():
        if not strategy_tasks:
            continue

        logger.info("Strategy: %s (%d tasks)", strategy, len(strategy_tasks))
        logger.info("-" * 60)

        for i, task in enumerate(strategy_tasks, 1):
            logger.info("  %d. %s", i, task.task_id)
            logger.info("     Origin: %s", task.origin)

            # Show first line of description
            first_line = task.description.split("\n")[0]
            if len(first_line) > 70:
                first_line = first_line[:67] + "..."
            logger.info("     Description: %s", first_line)

            if task.related_files:
                logger.info("     Related files: %s", ", ".join(task.related_files[:3]))

            if task.acceptance_criteria:
                logger.info("     Criteria: %s", task.acceptance_criteria[0])

        logger.info("")

    if args.dry_run:
        logger.info("\n[DRY RUN] Would execute %d tasks", len(tasks))
        logger.info("To actually execute, run without --dry-run")
    else:
        logger.info("\n[NOT IMPLEMENTED] Task execution would happen here")
        logger.info("Use scripts/run_evolution_loop.py for actual execution")

    logger.info("\n" + "=" * 60)
    logger.info("Demo complete!")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
