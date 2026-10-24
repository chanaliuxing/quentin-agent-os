#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
from datetime import datetime, UTC
from pathlib import Path

from meta_agent.self_programming.meta_experiment import (
    MetaExperimentOrchestrator,
    create_default_variants,
)
from meta_agent.self_programming.metrics_store import JsonlMetricsStore
from meta_agent.self_programming.strategy import StrategyType


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Run a meta-experiment comparing evolution strategy weights.")
    p.add_argument("--repo-root", default=".", help="Repo root (default: .)")
    p.add_argument("--experiment-id", default="", help="Experiment id (default: auto timestamped).")
    p.add_argument(
        "--metrics-file",
        default="data/research/meta_experiment_metrics.jsonl",
        help="Metrics JSONL relative to repo-root (default: data/research/meta_experiment_metrics.jsonl).",
    )
    p.add_argument(
        "--out",
        default="data/experiments/meta_experiment_result.json",
        help="Output JSON path relative to repo-root (default: data/experiments/meta_experiment_result.json).",
    )
    p.add_argument("--task-limit-per-variant", type=int, default=5, help="Tasks per variant (default: 5).")
    p.add_argument("--time-window-hours", type=int, default=24, help="Lookback window for run metrics (default: 24).")
    p.add_argument(
        "--primary-metric",
        type=str,
        default="success_rate",
        choices=["success_rate", "complexity_reduction", "coverage_improvement"],
        help="Primary metric for picking a winner (default: success_rate).",
    )
    p.add_argument("--learning-rate", type=float, default=0.1, help="Weight adjustment learning rate (default: 0.1).")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = Path(args.repo_root).resolve()

    exp_id = str(args.experiment_id).strip()
    if not exp_id:
        exp_id = f"meta_exp_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}"

    metrics_store = JsonlMetricsStore(repo_root=repo_root, filename=str(args.metrics_file))
    orch = MetaExperimentOrchestrator(metrics_store=metrics_store, repo_root=str(repo_root))

    variants = create_default_variants()
    experiment = orch.create_experiment(experiment_id=exp_id, variants=variants)
    experiment = orch.run_experiment(
        experiment,
        task_limit_per_variant=max(1, int(args.task_limit_per_variant)),
        time_window_hours=max(0, int(args.time_window_hours)),
    )
    winner, confidence = orch.analyze_results(experiment, primary_metric=str(args.primary_metric))

    current_weights = {StrategyType(k): float(v) for k, v in variants[0].weights.items()}
    new_weights = orch.auto_adjust_weights(current_weights=current_weights, experiment=experiment, learning_rate=float(args.learning_rate))

    out_path = Path(str(args.out))
    if not out_path.is_absolute():
        out_path = (repo_root / out_path).resolve()
    orch.save_experiment(experiment, output_path=out_path)

    summary = {
        "experiment_id": exp_id,
        "winner": winner.variant_id if winner else None,
        "confidence": float(confidence),
        "new_weights": {str(k): float(v) for k, v in new_weights.items()},
        "out": str(out_path),
    }
    print(json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

