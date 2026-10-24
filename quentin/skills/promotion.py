from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, asdict, field
from typing import Optional, Dict, Any, List

from quentin.skills.models import SkillCandidate, SkillDefinition
from quentin.skills.registry import FileBackedSkillRegistry
from quentin.skills.eval import SkillEvalHarness, SkillEvalReport
from quentin.l3.research.experiments import ResearchManager, Experiment
from quentin.utils.time import now_iso

logger = logging.getLogger(__name__)


@dataclass
class SkillPromotionResult:
    """
    一次晋升尝试的结果。

    - candidate_id : 候选技能 ID
    - status       : "promoted" / "skipped" / "rejected" / "error"
    - skill_id     : 若晋升成功，则为新 SkillDefinition 的 ID
    - eval_report  : SkillEvalReport.to_dict()
    - reasons      : 说明（列表）
    """
    candidate_id: str
    status: str
    skill_id: Optional[str]
    eval_report: Optional[Dict[str, Any]]
    reasons: List[str]
    created_at: str = field(default_factory=now_iso)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class SkillPromotionEngine:
    """
    SkillCandidate -> SkillDefinition 的推广引擎。

    v1 设计：

      - 从 SkillRegistry 读取候选技能
      - 用 SkillEvalHarness 做一个最小评估（完整度检查）
      - 若 eval.ok，则注册为正式 SkillDefinition，并删除 Candidate
      - 将结果写入 ResearchManager（方便做研究统计）

    后续可以挂接：
      - SafetyKernel（如果真正改动 Python 源文件时）
      - MultiAICouncil 做 promotion 审核
      - EvalHarness 做更复杂的回归与对比
    """

    def __init__(
        self,
        *,
        registry: Optional[FileBackedSkillRegistry] = None,
        eval_harness: Optional[SkillEvalHarness] = None,
        research_manager: Optional[ResearchManager] = None,
    ) -> None:
        self.registry = registry or FileBackedSkillRegistry()
        self.eval_harness = eval_harness or SkillEvalHarness()
        self.research_manager = research_manager or ResearchManager()

    # ---------- 对外主入口 ----------

    def promote_candidate(
        self,
        candidate_id: str,
        *,
        auto: bool = False,
    ) -> SkillPromotionResult:
        """
        尝试晋升一个指定的 SkillCandidate。

        auto=True 时可以用来做批量自动晋升（未来只允许低风险、评分很高的候选）。
        """
        cand = self.registry.get_candidate(candidate_id)
        if not cand:
            return SkillPromotionResult(
                candidate_id=candidate_id,
                status="error",
                skill_id=None,
                eval_report=None,
                reasons=[f"SkillCandidate not found: {candidate_id}"],
            )

        eval_report: SkillEvalReport = self.eval_harness.evaluate_candidate(cand)

        reasons: List[str] = []
        if not eval_report.ok:
            reasons.append("Evaluation failed; candidate not promoted.")
            res = SkillPromotionResult(
                candidate_id=candidate_id,
                status="rejected",
                skill_id=None,
                eval_report=eval_report.to_dict(),
                reasons=reasons + eval_report.issues,
            )
            # 记录到 ResearchManager
            self._record_promotion_run(cand, res)
            return res

        # v1：通过评估就直接晋升为正式 SkillDefinition
        skill_id = str(uuid.uuid4())
        skill = SkillDefinition(
            skill_id=skill_id,
            name=cand.name,
            domain=cand.domain,
            description=cand.description,
            input_schema={},      # 可以后续手工/AI补充
            output_schema={},
            code=cand.code,
            tests=cand.tests,
            tags=["auto-mined"],
            created_from_task_id=cand.from_task_id,
            supersedes=[],
            metadata={
                "source_candidate_id": cand.candidate_id,
                "promotion_auto": auto,
            },
        )

        self.registry.upsert_skill(skill)
        # v1：晋升成功后保留 candidate 还是删掉？
        #   - 这里选择保留，以便将来可以重评 / 对比。
        #   - 如果你想删，可以开启这行：
        # self.registry.delete_candidate(cand.candidate_id)

        reasons.append("Evaluation passed; candidate promoted to SkillDefinition.")

        res = SkillPromotionResult(
            candidate_id=cand.candidate_id,
            status="promoted",
            skill_id=skill_id,
            eval_report=eval_report.to_dict(),
            reasons=reasons,
        )

        self._record_promotion_run(cand, res)
        return res

    # ---------- ResearchManager 集成 ----------

    def _record_promotion_run(
        self,
        cand: SkillCandidate,
        res: SkillPromotionResult,
    ) -> None:
        """
        把这次晋升尝试记录为一个 experiment run：
          - capability   : skills:<domain>
          - requirement  : skill_quality
          - purpose      : skill_promotion
          - metrics      : eval_score / promoted / rejected
        """
        capability = f"skills:{cand.domain}"
        requirement_id = "skill_quality"

        exp = self._get_or_create_experiment(
            capability=capability,
            requirement_id=requirement_id,
        )

        eval_report = res.eval_report or {}
        score = float(eval_report.get("score") or 0.0)
        promoted = int(res.status == "promoted")
        rejected = int(res.status == "rejected")

        metrics = {
            "eval_score": score,
            "promoted": promoted,
            "rejected": rejected,
        }
        context = {
            "candidate_id": cand.candidate_id,
            "name": cand.name[:100],
            "domain": cand.domain,
            "status": res.status,
        }

        self.research_manager.record_run(
            experiment_id=exp.experiment_id,
            variant_id="auto" if res.eval_report else "manual",
            metrics=metrics,
            context=context,
        )

    def _get_or_create_experiment(
        self,
        *,
        capability: str,
        requirement_id: str,
    ) -> Experiment:
        exps = self.research_manager.list_experiments()
        for e in exps:
            if (
                e.capability == capability
                and e.requirement_id == requirement_id
                and e.purpose == "skill_promotion"
            ):
                return e

        return self.research_manager.create_experiment(
            name=f"SkillPromotion-{capability}-{requirement_id}",
            purpose="skill_promotion",
            capability=capability,
            requirement_id=requirement_id,
            tags=["skills", "promotion"],
        )
