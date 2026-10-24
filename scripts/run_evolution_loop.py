"""
Simple daemon for running the self-programming evolution loop.
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

# Add repo root to Python path
repo_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(repo_root))

from meta_agent.self_programming.engine import SelfProgrammingEngine
from meta_agent.self_programming.metrics_store import JsonlMetricsStore
from meta_agent.self_programming.strategy import EvolutionStrategyManager, SimpleEvolutionStrategyManager
from meta_agent.self_programming.evolution_loop import run_loop

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the self-programming evolution loop.")
    parser.add_argument("--sleep-seconds", type=int, default=30, help="Sleep duration when no tasks are found.")
    parser.add_argument("--max-iterations", type=int, default=0, help="Number of iterations before exiting (0 = infinite).")
    parser.add_argument(
        "--strategy",
        type=str,
        default="multi",
        choices=["multi", "simple"],
        help="Task generation strategy manager (default: multi).",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    repo_root = Path(__file__).resolve().parents[1]

    metrics_store = JsonlMetricsStore(repo_root=repo_root)
    engine = SelfProgrammingEngine(repo_root=str(repo_root), metrics_store=metrics_store)
    if args.strategy == "simple":
        strategy_manager = SimpleEvolutionStrategyManager(metrics_store=metrics_store)
    else:
        strategy_manager = EvolutionStrategyManager(metrics_store=metrics_store, repo_root=str(repo_root))

    max_iters = None if args.max_iterations <= 0 else args.max_iterations
    logger.info(
        "Starting evolution loop (strategy=%s, sleep=%ss, iterations=%s)",
        args.strategy,
        args.sleep_seconds,
        max_iters or "∞",
    )
    run_loop(
        strategy_manager=strategy_manager,
        engine=engine,
        sleep_seconds=args.sleep_seconds,
        max_iterations=max_iters,
    )


if __name__ == "__main__":
    main()
