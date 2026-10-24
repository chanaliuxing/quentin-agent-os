"""
运行一次完整的“蓝皮书自我改进循环”。

功能：
  1. 初始化 RuntimeFacade（带 council、多 loop、自编程引擎等）
  2. 调用 ResearchLayer.run_blueprint_improvement_cycle(...)
  3. 把这次 cycle 的结果写入 data/blueprint/runs/ 下的 JSON 报告

用法（在 repo 根目录）：

  # 只跑一次，默认最多处理 5 个 gap
  python -m scripts.run_blueprint_cycle

  # 指定最多处理的 gap 数量
  python -m scripts.run_blueprint_cycle --max-gaps 10

  # 指定 repo 根目录（不写就是当前目录）
  python -m scripts.run_blueprint_cycle --repo-root /path/to/repo
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

from quentin.runtime.system import RuntimeFacade
from scripts.blueprint_self_iterate import create_runtime_for_blueprint_self_iteration
from quentin.metrics.aggregator import MetricsAggregator


def _now_ts() -> str:
    # 用 UTC 时间生成文件名友好的时间戳
    return datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")


def _print_summary(result: Dict[str, Any]) -> None:
    status = result.get("status", "unknown")
    gaps = result.get("gaps", [])
    modules = result.get("modules_to_improve", [])
    sp = result.get("self_programming_summary", {}) or {}

    print("=== Blueprint Improvement Cycle ===")
    print("status             :", status)
    print("num_gaps           :", len(gaps))
    print("num_modules_to_fix :", len(modules))
    print("self_programming   :")
    print("  status           :", sp.get("status", "n/a"))
    print("  num_targets      :", sp.get("num_targets", 0))
    print("  num_proposals    :", sp.get("num_proposals", 0))
    print("  experiment_ids   :", sp.get("experiment_ids", []))


def main() -> None:
    parser = argparse.ArgumentParser(description="Run one blueprint improvement cycle.")
    parser.add_argument(
        "--repo-root",
        type=str,
        default=".",
        help="Repository root (default: current directory).",
    )
    parser.add_argument(
        "--max-gaps",
        type=int,
        default=5,
        help="Max number of blueprint gaps to handle in this cycle.",
    )
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()

    # 1) 初始化 runtime（带 council + loops + research_layer + self_programming_engine）
    runtime: RuntimeFacade = create_runtime_for_blueprint_self_iteration(repo_root=repo_root)

    if runtime.research_layer is None:
        raise RuntimeError("runtime.research_layer is None. 请检查 create_runtime_for_blueprint_self_iteration 实现。")

    research_layer = runtime.research_layer

    # 2) 采集最近的指标（来自 Trace + ImmuneLoop）
    metrics_agg = MetricsAggregator(repo_root=repo_root)
    recent_metrics = metrics_agg.compute_recent_metrics(
        max_events=2000,
        window_seconds=None,  # 你也可以改成 3600 表示只看最近 1 小时
    )

    # ImmuneLoop 快照：看系统最近一次免疫动作
    try:
        immune_action = runtime.run_immune_check()
        immune_snapshot = {
            "action_type": getattr(immune_action, "action_type", None),
            "reason": getattr(immune_action, "reason", None),
            "metadata": getattr(immune_action, "metadata", {}),
        }
    except Exception as e:
        immune_snapshot = {
            "action_type": "error",
            "reason": f"run_immune_check_failed: {e!r}",
            "metadata": {},
        }

    research_request = {
        "metrics": {
            "recent": recent_metrics,
            "immune_snapshot": immune_snapshot,
            "note": "blueprint improvement cycle with real metrics",
        }
    }

    # 3) 运行蓝皮书自迭代循环
    result = research_layer.run_blueprint_improvement_cycle(
        runtime=runtime,
        max_gaps=args.max_gaps,
        research_request=research_request,
    )

    # 4) 写入 JSON 报告到 data/blueprint/runs/
    runs_dir = repo_root / "data" / "blueprint" / "runs"
    runs_dir.mkdir(parents=True, exist_ok=True)

    ts = _now_ts()
    out_path = runs_dir / f"blueprint_cycle_{ts}.json"
    tmp = out_path.with_suffix(".tmp")

    with tmp.open("w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    tmp.replace(out_path)

    # 5) 控制台输出简要 summary
    _print_summary(result)
    print("report_path        :", out_path)


if __name__ == "__main__":
    main()
