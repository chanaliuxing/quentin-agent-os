# meta_agent/blueprint/objective_eval.py
from __future__ import annotations
from dataclasses import dataclass
from typing import List, Dict, Any, Optional
import datetime as dt

from meta_agent.blueprint.coverage import (
    BlueprintCoverageReport,
    SectionCoverage,
)
from meta_agent.blueprint.objectives import (
    BlueprintObjectives,
    SectionObjective,
    GlobalObjective,
)


@dataclass
class SectionPriority:
    section_id: str
    path: str
    title: str
    current_level: str
    target_level: str
    weight: float
    urgency_score: float
    gap_score: float
    overall_score: float
    reason: str


@dataclass
class GlobalProgressStatus:
    expected_self_evolving: int
    current_self_evolving: int
    behind_by: int
    progress_ratio: float
    target_date: Optional[str]


@dataclass
class ObjectiveEvalResult:
    global_status: Optional[GlobalProgressStatus]
    section_priorities: List[SectionPriority]


class BlueprintObjectiveEvaluator:
    LEVEL_ORDER = {
        "missing": 0,
        "planned": 1,
        "implemented": 2,
        "evaluated": 3,
        "self_evolving": 4,
    }

    def __init__(self, *, today: Optional[dt.date] = None) -> None:
        self.today = today or dt.date.today()

    def evaluate(
        self,
        coverage: BlueprintCoverageReport,
        objectives: BlueprintObjectives,
    ) -> ObjectiveEvalResult:
        global_status = self._eval_global(coverage, objectives.global_obj)
        section_priorities = self._eval_sections(coverage, objectives.sections)

        section_priorities.sort(key=lambda p: p.overall_score, reverse=True)

        return ObjectiveEvalResult(
            global_status=global_status,
            section_priorities=section_priorities,
        )

    def _eval_global(
        self,
        coverage: BlueprintCoverageReport,
        global_obj: Optional[GlobalObjective],
    ) -> Optional[GlobalProgressStatus]:
        if not global_obj:
            return None

        current_self_evo = coverage.summary.count_self_evolving
        target = global_obj.target_self_evolving_sections

        # ✅ 不再按天数线性插值，expected 就是最终目标
        expected = target if target > 0 else current_self_evo

        behind_by = max(expected - current_self_evo, 0)
        progress_ratio = (current_self_evo / expected) if expected > 0 else 1.0

        return GlobalProgressStatus(
            expected_self_evolving=expected,   # 直接等于目标
            current_self_evolving=current_self_evo,
            behind_by=behind_by,
            progress_ratio=progress_ratio,
            target_date=global_obj.target_date,
        )

    def _eval_sections(
        self,
        coverage: BlueprintCoverageReport,
        section_objs: Dict[str, SectionObjective],
    ) -> List[SectionPriority]:
        pri_list: List[SectionPriority] = []
        cov_by_id: Dict[str, SectionCoverage] = {s.section_id: s for s in coverage.sections}

        for sec_id, obj in section_objs.items():
            cov = cov_by_id.get(sec_id)
            current_level = cov.level if cov else "missing"
            
            level_gap = max(0, self.LEVEL_ORDER.get(obj.target_level, 0) - self.LEVEL_ORDER.get(current_level, 0))

            urgency = 0.0
            reason_parts = []
            if obj.target_date:
                try:
                    target_date = dt.date.fromisoformat(obj.target_date)
                    days_left = (target_date - self.today).days
                    if days_left <= 0: urgency = 1.0; reason_parts.append("Overdue")
                    elif days_left <= 7: urgency = 0.9; reason_parts.append(f"{days_left} days left")
                    elif days_left <= 30: urgency = 0.6
                    else: urgency = 0.3
                except Exception: urgency = 0.5
            else: urgency = 0.4

            gap_score = level_gap
            if cov:
                gap_score += 0.2 * cov.open_gaps + 0.1 * cov.open_todos
                if cov.open_gaps > 0: reason_parts.append(f"{cov.open_gaps} open gaps")
                if cov.open_todos > 0: reason_parts.append(f"{cov.open_todos} TODOs")

            overall = obj.weight * (urgency + gap_score)
            reason = "; ".join(reason_parts) or "No specific reason"

            pri_list.append(
                SectionPriority(
                    section_id=sec_id, path=cov.path if cov else sec_id, title=cov.title if cov else sec_id,
                    current_level=current_level, target_level=obj.target_level, weight=obj.weight,
                    urgency_score=urgency, gap_score=gap_score, overall_score=overall, reason=reason,
                )
            )
        return pri_list
