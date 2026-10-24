"""
批量治理所有已有 PatchReport，并可选自动在 sandbox 环境应用补丁。

用法（在 repo 根目录）：

  # 只对推荐 action = \"accept\" 的 patch 做治理，不自动应用
  python -m scripts.auto_govern_all_patches --only-recommended accept

  # 对所有 patch 做治理（不筛选 recommended_action），也不自动应用
  python -m scripts.auto_govern_all_patches

  # 对推荐 accept 的 patch 做治理，并在安全内核允许的前提下自动应用
  python -m scripts.auto_govern_all_patches --only-recommended accept --auto-apply
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import List, Optional

from quentin.runtime.system import RuntimeFacade
from scripts.blueprint_self_iterate import create_runtime_for_blueprint_self_iteration
from quentin.traces.core import JsonlTraceRecorder
from quentin.metrics.aggregator import MetricsAggregator
from quentin.governance.patch_council import PatchGovernanceCouncil
from quentin.governance.batch import BatchPatchGovernor


def _parse_only_recommended(raw: Optional[str]) -> Optional[List[str]]:
    if not raw:
        return None
    # 支持逗号分隔： "accept,reject"
    items = [x.strip() for x in raw.split(",") if x.strip()]
    return items or None


def main() -> None:
    parser = argparse.ArgumentParser(description="Batch govern all patch reports with AI council and safety kernel.")
    parser.add_argument("--repo-root", type=str, default=".", help="Repository root (default: current dir).")
    parser.add_argument(
        "--only-recommended",
        type=str,
        default=None,
        help="Only process patch reports whose 'recommended_action' in this list "
             "(comma separated, e.g. 'accept,needs_review'). Default: no filter.",
    )
    parser.add_argument(
        "--auto-apply",
        action="store_true",
        help="If set, allow governance council + safety kernel to automatically apply patches in sandbox.",
    )
    parser.add_argument(
        "--max-patches",
        type=int,
        default=None,
        help="Max number of patches to process in this batch.",
    )
    parser.add_argument(
        "--max-events",
        type=int,
        default=2000,
        help="Max events to scan from trace when computing recent metrics.",
    )
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()

    # 1) 初始化 runtime（带 council、loops、research_layer 等）
    runtime: RuntimeFacade = create_runtime_for_blueprint_self_iteration(repo_root=repo_root)

    # 2) 收集最近 metrics + ImmuneLoop snapshot
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

    # 3) 构造 PatchGovernanceCouncil + BatchPatchGovernor
    recorder = JsonlTraceRecorder(repo_root=repo_root)
    council_callable = getattr(runtime, "council", None) or runtime.model_router

    patch_council = PatchGovernanceCouncil(
        repo_root=repo_root,
        council_callable=council_callable,
        trace_recorder=recorder,
    )
    batch_governor = BatchPatchGovernor(
        repo_root=repo_root,
        patch_council=patch_council,
    )

    only_rec = _parse_only_recommended(args.only_recommended)

    # 4) 执行批量治理
    result = batch_governor.auto_govern_all(
        metrics=recent_metrics,
        immune_snapshot=immune_snapshot,
        auto_apply=args.auto_apply,
        only_recommended=only_rec,
        max_patches=args.max_patches,
    )

    # 5) 控制台输出 summary
    print("=== Batch Patch Governance Result ===")
    print("total_reports :", result.total_reports)
    print("processed     :", result.processed)
    print("skipped       :", result.skipped)
    print("started_at    :", result.started_at)
    print("finished_at   :", result.finished_at)
    print("decisions     :", len(result.decisions))

    for d in result.decisions:
        print("- proposal_id       :", d.proposal_id)
        print("  action           :", d.recommended_action)
        print("  env              :", d.environment)
        print("  risk_level       :", d.risk_level)
        print("  auto_apply       :", d.auto_apply)
        print("  rationale        :", d.rationale[:200].replace("\n", " "))
        if "apply_log" in d.constraints:
            log = d.constraints["apply_log"]
            print("  apply_status     :", log.get("status"))
            print("  apply_target     :", log.get("target_path"))
            print("  apply_backup     :", log.get("backup_path"))
        print()
    

if __name__ == "__main__":
    main()
