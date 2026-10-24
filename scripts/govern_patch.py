"""
对某个 PatchProposal 进行治理决策（多 AI 理事会 + 安全内核），可选自动在 sandbox 应用。

用法（在 repo 根目录）：

  # 只做决策，不自动应用
  python -m scripts.govern_patch --proposal-id patch-1234

  # 做决策，并在安全前提下自动尝试在 sandbox 环境 apply
  python -m scripts.govern_patch --proposal-id patch-1234 --auto-apply
"""

from __future__ import annotations

import argparse
from pathlib import Path

from quentin.traces.core import JsonlTraceRecorder
from quentin.runtime.system import RuntimeFacade
from scripts.blueprint_self_iterate import create_runtime_for_blueprint_self_iteration
from quentin.metrics.aggregator import MetricsAggregator
from quentin.governance.patch_council import PatchGovernanceCouncil


def main() -> None:
    parser = argparse.ArgumentParser(description="Govern a patch proposal with AI council and safety kernel.")
    parser.add_argument("--repo-root", type=str, default=".", help="Repository root (default: current dir).")
    parser.add_argument("--proposal-id", required=True, help="Patch proposal_id.")
    parser.add_argument(
        "--auto-apply",
        action="store_true",
        help="If set, allow governance council + safety kernel to automatically apply the patch in sandbox.",
    )
    parser.add_argument(
        "--max-events",
        type=int,
        default=2000,
        help="Max events to scan from trace when computing recent metrics.",
    )
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()

    # 1) 初始化 runtime（含 council, experiment_orchestrator, research_layer 等）
    runtime: RuntimeFacade = create_runtime_for_blueprint_self_iteration(repo_root=repo_root)

    # 2) 采集最近指标 + ImmuneLoop 快照
    metrics_agg = MetricsAggregator(repo_root=repo_root)
    recent_metrics = metrics_agg.compute_recent_metrics(
        max_events=args.max_events,
        window_seconds=None,
    )

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

    # 3) 构造治理理事会
    recorder = JsonlTraceRecorder(repo_root=repo_root)
    council_callable = getattr(runtime, "council", None) or runtime.model_router
    patch_council = PatchGovernanceCouncil(
        repo_root=repo_root,
        council_callable=council_callable,
        trace_recorder=recorder,
    )

    # 4) 执行治理决策
    decision = patch_council.govern_patch(
        proposal_id=args.proposal_id,
        metrics=recent_metrics,
        immune_snapshot=immune_snapshot,
        auto_apply=args.auto_apply,
    )

    # 5) 控制台输出摘要
    print("=== Patch Governance Decision ===")
    print("proposal_id        :", decision.proposal_id)
    print("recommended_action :", decision.recommended_action)
    print("environment        :", decision.environment)
    print("risk_level         :", decision.risk_level)
    print("auto_apply         :", decision.auto_apply)
    print("decided_at         :", decision.decided_at)
    print("rationale          :", decision.rationale)

    if "apply_log" in decision.constraints:
        print("--- apply_log (short) ---")
        log = decision.constraints["apply_log"]
        print("  status     :", log.get("status"))
        print("  target     :", log.get("target_path"))
        print("  backup     :", log.get("backup_path"))
        print("  dry_run    :", log.get("dry_run"))
        print("  applied_at :", log.get("applied_at"))


if __name__ == "__main__":
    main()
