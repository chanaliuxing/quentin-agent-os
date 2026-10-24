"""
命令行查看蓝皮书自迭代的整体进度。

用法（在仓库根目录）：
    python -m scripts.metrics_summary

可选参数：
    --runs-dir PATH   指定 runs 目录（默认 data/runs/blueprint_self_iterate）
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from quentin.metrics.aggregator import (
    load_run_metrics_from_dir,
    summarize_progress,
    to_timeseries,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Show summary of blueprint self-iteration progress.")
    parser.add_argument(
        "--runs-dir",
        type=str,
        default="data/runs/blueprint_self_iterate",
        help="Directory containing metrics_*.json files.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output full summary as JSON (otherwise print human-readable text).",
    )
    args = parser.parse_args()

    runs_dir = Path(args.runs_dir).resolve()
    metrics_list = load_run_metrics_from_dir(runs_dir)

    if not metrics_list:
        print(f"No metrics_*.json found in {runs_dir}")
        return

    summary = summarize_progress(metrics_list)

    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return

    # 人类可读模式
    print("==== Blueprint Self-Iteration Summary ====")
    print(f"Runs directory : {runs_dir}")
    print(f"Total runs     : {summary['total_runs']}")

    first = summary["first_run"]
    latest = summary["latest_run"]
    improvement = summary["improvement"]

    if first and latest:
        print("\n-- First run --")
        print(f"  run_id       : {first['run_id']}")
        print(f"  started_at   : {first['started_at']}")
        print(f"  total caps   : {first['total_capabilities']}")
        print(f"  done         : {first['num_done']}")
        print(f"  missing      : {first['num_missing']}")
        print(f"  partial      : {first['num_partial']}")
        print(f"  unknown      : {first['num_unknown']}")

        print("\n-- Latest run --")
        print(f"  run_id       : {latest['run_id']}")
        print(f"  started_at   : {latest['started_at']}")
        print(f"  total caps   : {latest['total_capabilities']}")
        print(f"  done         : {latest['num_done']}")
        print(f"  missing      : {latest['num_missing']}")
        print(f"  partial      : {latest['num_partial']}")
        print(f"  unknown      : {latest['num_unknown']}")

        if improvement:
            print("\n-- Improvement (first -> latest) --")
            print(f"  done_increase      : {improvement['done_increase']}")
            print(f"  missing_decrease   : {improvement['missing_decrease']}")
            print(f"  done_ratio_change  : {improvement['done_ratio_change']:.4f}")
            print(f"  missing_ratio_change: {improvement['missing_ratio_change']:.4f}")

    avg_success = summary["avg_experiment_success_rate"]
    if avg_success is not None:
        print(f"\nAvg experiment success rate: {avg_success:.3f}")

    print("\nTip: run with --json to get a machine-readable summary.")


if __name__ == "__main__":
    main()
