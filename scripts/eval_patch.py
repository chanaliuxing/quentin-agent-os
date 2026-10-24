"""
对某个 PatchProposal 进行离线评测，生成 PatchReport。

用法（在 repo 根目录）：

  # 对 proposal_id=patch-1234，用 test_suite_id=planner_basic 做评测
  python -m scripts.eval_patch --proposal-id patch-1234 --test-suite-id planner_basic

  # 指定 baseline / candidate 运行时 variant 名称
  python -m scripts.eval_patch --proposal-id patch-1234 --test-suite-id planner_basic \
      --baseline baseline --candidate council
"""

from __future__ import annotations

import argparse
from pathlib import Path

from quentin.traces.core import JsonlTraceRecorder
from quentin.runtime.system import RuntimeFacade
from scripts.blueprint_self_iterate import create_runtime_for_blueprint_self_iteration
from quentin.self_programming.eval import PatchEvaluator


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate a patch proposal with a test suite.")
    parser.add_argument("--repo-root", type=str, default=".", help="Repository root.")
    parser.add_argument("--proposal-id", required=True, help="Patch proposal_id.")
    parser.add_argument("--test-suite-id", required=True, help="Test suite id (under data/tests/patches).")
    parser.add_argument("--baseline", type=str, default="baseline", help="Baseline runtime variant name.")
    parser.add_argument("--candidate", type=str, default="council", help="Candidate runtime variant name.")
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()

    # 1) 初始化 runtime（里边已经有 baseline / council / research_layer 等）
    runtime: RuntimeFacade = create_runtime_for_blueprint_self_iteration(repo_root=repo_root)

    # 2) 构造 evaluator
    recorder = JsonlTraceRecorder(repo_root=repo_root)
    evaluator = PatchEvaluator(
        repo_root=repo_root,
        experiment_orchestrator=runtime.research_layer.experiment_orchestrator, # Access via research_layer
        trace_recorder=recorder,
    )

    # 3) 跑评测
    report = evaluator.evaluate_patch(
        proposal_id=args.proposal_id,
        test_suite_id=args.test_suite_id,
        baseline_variant=args.baseline,
        candidate_variant=args.candidate,
    )

    # 4) 打印摘要
    print("=== Patch Evaluation Report ===")
    print("proposal_id        :", report["proposal"]["proposal_id"])
    print("target_path        :", report["proposal"]["target"]["path"])
    print("recommended_action :", report["recommended_action"])
    print("reasoning          :", report["reasoning"])

    metrics = (report.get("execution_result") or {}).get("metrics_delta", {})
    if metrics:
        print("baseline_score     :", metrics.get("baseline_score"))
        print("candidate_score    :", metrics.get("candidate_score"))
        print("delta              :", metrics.get("delta_candidate_minus_baseline"))


if __name__ == "__main__":
    main()
