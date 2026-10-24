from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, List, Optional

import json

from quentin.self_programming.schema import (
    PatchProposal,
    PatchTarget,
    PatchTestPlan,
    PatchExecutionResult,
    PatchReport,
)
from quentin.eval.harness import EvalCase
from quentin.traces.core import TraceRecorder, TraceEventType, new_trace_event
from quentin.l3.research.experiments import ExperimentOrchestrator
from quentin.utils.time import now_iso, now_utc


def _now_iso() -> str:
    return now_iso()


def load_patch_proposal(
    repo_root: str | Path,
    proposal_id: str,
) -> Optional[PatchProposal]:
    """
    通用的 PatchProposal loader，避免在多个地方复制逻辑。
    """
    repo_root = Path(repo_root).resolve()
    proposals_dir = repo_root / "data" / "patches" / "proposals"
    path = proposals_dir / f"{proposal_id}.json"
    if not path.exists():
        return None

    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    target = PatchTarget(**data["target"])
    test_plan = PatchTestPlan(**data.get("test_plan", {}))

    proposal = PatchProposal(
        proposal_id=data["proposal_id"],
        created_at=data["created_at"],
        created_by=data["created_by"],
        target=target,
        rationale=data["rationale"],
        patch_type=data["patch_type"],
        patch_content=data["patch_content"],
        test_plan=test_plan,
        meta=data.get("meta", {}),
    )
    return proposal


class PatchEvaluator:
    """
    Patch 离线评测器：

      - 从 data/tests/patches/<test_suite_id>.json 里加载评测用例
      - 使用 ExperimentOrchestrator.run_prompt_eval_experiment(...) 跑多 variant
      - 按 baseline_variant vs candidate_variant 做对比
      - 生成 PatchExecutionResult + PatchReport，写入 data/patches/reports/
    """

    def __init__(
        self,
        *,
        repo_root: str | Path,
        experiment_orchestrator: ExperimentOrchestrator,
        trace_recorder: TraceRecorder,
    ) -> None:
        self.repo_root = Path(repo_root).resolve()
        self.experiment_orchestrator = experiment_orchestrator
        self.trace_recorder = trace_recorder

        self._tests_dir = self.repo_root / "data" / "tests" / "patches"
        self._reports_dir = self.repo_root / "data" / "patches" / "reports"
        self._reports_dir.mkdir(parents=True, exist_ok=True)

    # --------------------------------------------------
    # 对外：对某个 proposal + 测试集做一次评测
    # --------------------------------------------------
    def evaluate_patch(
        self,
        *,
        proposal_id: str,
        test_suite_id: str,
        baseline_variant: str = "baseline",
        candidate_variant: str = "council",
    ) -> Dict[str, Any]:
        """
        跑一次评测并返回 PatchReport 的 dict 结构。
        """
        proposal = load_patch_proposal(self.repo_root, proposal_id)
        if proposal is None:
            raise FileNotFoundError(f"PatchProposal {proposal_id} not found.")

        test_suite = self._load_test_suite(test_suite_id)
        eval_cases = self._build_eval_cases(test_suite)

        experiment_id = f"{proposal_id}-{test_suite_id}-{now_utc().strftime('%Y%m%dT%H%M%S')}"
        variants = [baseline_variant, candidate_variant]

        # 1) 调用 ExperimentOrchestrator 运行评测
        eval_results = self.experiment_orchestrator.run_prompt_eval_experiment(
            experiment_id=experiment_id,
            cases=[c.to_dict() for c in eval_cases],
            variants=variants,
        )

        # 2) 汇总指标 → PatchExecutionResult
        execution_result = self._build_execution_result(
            proposal_id=proposal_id,
            eval_results=eval_results,
            baseline_variant=baseline_variant,
            candidate_variant=candidate_variant,
        )

        # 3) 根据指标差异给出推荐动作 → PatchReport
        report = self._build_patch_report(
            proposal=proposal,
            execution_result=execution_result,
            baseline_variant=baseline_variant,
            candidate_variant=candidate_variant,
        )

        # 4) 落盘 + 写 TraceEvent
        self._persist_patch_report(report)
        self._record_trace(report)

        return report.to_dict()

    # --------------------------------------------------
    # 内部：加载测试集 & 构造 EvalCase
    # --------------------------------------------------
    def _load_test_suite(self, test_suite_id: str) -> Dict[str, Any]:
        path = self._tests_dir / f"{test_suite_id}.json"
        if not path.exists():
            raise FileNotFoundError(
                f"Test suite not found: {path}. 请在 data/tests/patches 下创建 {test_suite_id}.json"
            )
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)

    def _build_eval_cases(self, suite: Dict[str, Any]) -> List[EvalCase]:
        cases_data = suite.get("cases", [])
        eval_cases: List[EvalCase] = []
        for c in cases_data:
            eval_cases.append(
                EvalCase(
                    case_id=c["case_id"],
                    description=c.get("description", ""),
                    input_payload=c.get("input_payload", {}),
                    expected_keywords=c.get("expected_keywords", []),
                )
            )
        return eval_cases

    # --------------------------------------------------
    # 内部：根据 eval_results 汇总 PatchExecutionResult
    # --------------------------------------------------
    def _build_execution_result(
        self,
        *,
        proposal_id: str,
        eval_results: List[Dict[str, Any]],
        baseline_variant: str,
        candidate_variant: str,
    ) -> PatchExecutionResult:
        """
        eval_results 是 run_prompt_eval_experiment 返回的 list[dict]：

          {
            "case_id": "...",
            "variant": "baseline" / "council" / ...,
            "raw_output": "...",
            "score": 0.0~1.0,
            "matched_keywords": [...]
          }
        """
        tests_run: List[str] = []
        tests_passed: List[str] = []
        tests_failed: List[str] = []

        # 记录 variant -> [scores]
        scores_by_variant: Dict[str, List[float]] = {}
        # 顺手统计多少 case 的得分 >= 0.8 视为“通过”
        for r in eval_results:
            key = f"{r['variant']}::{r['case_id']}"
            tests_run.append(key)

            score = float(r.get("score", 0.0))
            variant = r["variant"]
            scores_by_variant.setdefault(variant, []).append(score)

            if score >= 0.8:
                tests_passed.append(key)
            else:
                tests_failed.append(key)

        avg_scores = {
            v: (sum(scores) / len(scores) if scores else 0.0)
            for v, scores in scores_by_variant.items()
        }

        baseline_score = avg_scores.get(baseline_variant, 0.0)
        candidate_score = avg_scores.get(candidate_variant, 0.0)

        metrics_delta: Dict[str, Any] = {
            "avg_scores": avg_scores,
            "baseline_variant": baseline_variant,
            "candidate_variant": candidate_variant,
            "baseline_score": baseline_score,
            "candidate_score": candidate_score,
            "delta_candidate_minus_baseline": candidate_score - baseline_score,
        }

        # 这里先不统计静态分析结果，留空
        execution_result = PatchExecutionResult(
            proposal_id=proposal_id,
            tests_run=tests_run,
            tests_passed=tests_passed,
            tests_failed=tests_failed,
            static_issues=[],
            metrics_delta=metrics_delta,
        )
        return execution_result

    # --------------------------------------------------
    # 内部：生成 PatchReport（推荐动作）
    # --------------------------------------------------
    def _build_patch_report(
        self,
        *,
        proposal: PatchProposal,
        execution_result: PatchExecutionResult,
        baseline_variant: str,
        candidate_variant: str,
    ) -> PatchReport:
        m = execution_result.metrics_delta
        baseline_score = float(m.get("baseline_score", 0.0))
        candidate_score = float(m.get("candidate_score", 0.0))
        delta = float(m.get("delta_candidate_minus_baseline", 0.0))

        # 非常简单的策略：
        #   - candidate 平均分 >= 0.8 且 比 baseline 高至少 0.05 → 推荐 accept
        #   - candidate 分明显更差（比 baseline 低 0.05） → 推荐 reject
        #   - 其它情况 → needs_review
        if candidate_score >= 0.8 and delta >= 0.05:
            recommended_action = "accept"
            reasoning = (
                f"Candidate variant '{candidate_variant}' 平均得分 {candidate_score:.3f}，"
                f"显著高于 baseline '{baseline_variant}' 的 {baseline_score:.3f}。"
            )
        elif delta <= -0.05:
            recommended_action = "reject"
            reasoning = (
                f"Candidate variant '{candidate_variant}' 平均得分 {candidate_score:.3f}，"
                f"明显低于 baseline '{baseline_variant}' 的 {baseline_score:.3f}。"
            )
        else:
            recommended_action = "needs_review"
            reasoning = (
                f"Candidate 与 baseline 差异不明显（baseline={baseline_score:.3f}, "
                f"candidate={candidate_score:.3f}, delta={delta:.3f}），建议人工或多 AI 理事会复核。"
            )

        report = PatchReport(
            proposal=proposal,
            execution_result=execution_result,
            recommended_action=recommended_action,
            reasoning=reasoning,
        )
        return report

    # --------------------------------------------------
    # 内部：落盘 & Trace
    # --------------------------------------------------
    def _persist_patch_report(self, report: PatchReport) -> None:
        proposal_id = report.proposal.proposal_id
        path = self._reports_dir / f"{proposal_id}.json"
        tmp = path.with_suffix(".tmp")

        with tmp.open("w", encoding="utf-8") as f:
            json.dump(report.to_dict(), f, ensure_ascii=False, indent=2)
        tmp.replace(path)

    def _record_trace(self, report: PatchReport) -> None:
        self.trace_recorder.record_event(
            new_trace_event(
                trace_id="self-programming",
                event_type=TraceEventType.SELF_PROGRAMMING,
                payload={
                    "patch_report": report.to_dict(),
                },
            )
        )
