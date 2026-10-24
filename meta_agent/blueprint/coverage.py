# meta_agent/blueprint/coverage.py
from __future__ import annotations
from quentin.utils.time import now_iso, now_utc
from dataclasses import dataclass, asdict
from typing import List, Dict, Any, Optional
import datetime as dt


@dataclass
class SectionCoverage:
    section_id: str
    path: str
    title: str
    spec_defined: bool
    impl_present: bool
    skills_attached: bool
    tested: bool
    self_evolving: bool
    open_gaps: int
    open_todos: int
    last_touched_at: Optional[str] = None
    level: str = "missing"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class BlueprintCoverageSummary:
    total_sections: int
    count_missing: int
    count_planned: int
    count_implemented: int
    count_evaluated: int
    count_self_evolving: int

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class BlueprintCoverageReport:
    generated_at: str
    summary: BlueprintCoverageSummary
    sections: List[SectionCoverage]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "generated_at": self.generated_at,
            "summary": self.summary.to_dict(),
            "sections": [s.to_dict() for s in self.sections],
        }


@dataclass
class BlueprintIndexItem:
    section_id: str
    path: str
    title: str


class BlueprintCoverageAnalyzer:
    def __init__(self) -> None:
        pass # No explicit dependencies in init for now

    def build_report(
        self,
        blueprint_index: List[BlueprintIndexItem],
        snapshot: Dict[str, Any],
    ) -> BlueprintCoverageReport:
        sections_cov: List[SectionCoverage] = []

        impl_map = snapshot.get("blueprint_impl_status", {})
        gap_map = snapshot.get("blueprint_gaps", {})
        skills_map = snapshot.get("blueprint_skills", {})
        test_map = snapshot.get("blueprint_tests", {})
        evo_map = snapshot.get("blueprint_self_evo", {})

        for item in blueprint_index:
            sec_id = item.section_id

            spec_defined = True
            impl_info = impl_map.get(sec_id) or {}
            gap_info = gap_map.get(sec_id) or {}
            skills_info = skills_map.get(sec_id) or {}
            test_info = test_map.get(sec_id) or {}
            evo_info = evo_map.get(sec_id) or {}

            impl_present = bool(impl_info.get("present", False))
            skills_attached = bool(skills_info.get("has_active_skills", False))
            tested = bool(test_info.get("has_tests", False) or test_info.get("runs", 0) > 0)
            self_evolving = bool(evo_info.get("touched_recently", False))

            open_gaps = int(gap_info.get("open_gaps", 0))
            open_todos = int(impl_info.get("open_todos", 0) or gap_info.get("open_todos", 0) or 0)
            last_touched_at = (
                evo_info.get("last_touched_at")
                or impl_info.get("last_changed_at")
                or test_info.get("last_run_at")
            )

            level = self._classify_level(
                spec_defined=spec_defined,
                impl_present=impl_present,
                skills_attached=skills_attached,
                tested=tested,
                self_evolving=self_evolving,
            )

            cov = SectionCoverage(
                section_id=sec_id,
                path=item.path,
                title=item.title,
                spec_defined=spec_defined,
                impl_present=impl_present,
                skills_attached=skills_attached,
                tested=tested,
                self_evolving=self_evolving,
                open_gaps=open_gaps,
                open_todos=open_todos,
                last_touched_at=last_touched_at,
                level=level,
            )
            sections_cov.append(cov)

        summary = self._build_summary(sections_cov)
        report = BlueprintCoverageReport(
            generated_at=now_iso(),
            summary=summary,
            sections=sections_cov,
        )
        return report

    def _classify_level(
        self,
        *,
        spec_defined: bool,
        impl_present: bool,
        skills_attached: bool,
        tested: bool,
        self_evolving: bool,
    ) -> str:
        if not spec_defined:
            return "missing"
        if not impl_present:
            return "planned"
        if self_evolving:
            return "self_evolving"
        if tested or skills_attached:
            return "evaluated"
        return "implemented"

    def _build_summary(self, sections: List[SectionCoverage]) -> BlueprintCoverageSummary:
        total = len(sections)
        cnt_missing = sum(1 for s in sections if s.level == "missing")
        cnt_planned = sum(1 for s in sections if s.level == "planned")
        cnt_impl = sum(1 for s in sections if s.level == "implemented")
        cnt_eval = sum(1 for s in sections if s.level == "evaluated")
        cnt_evo = sum(1 for s in sections if s.level == "self_evolving")

        return BlueprintCoverageSummary(
            total_sections=total,
            count_missing=cnt_missing,
            count_planned=cnt_planned,
            count_implemented=cnt_impl,
            count_evaluated=cnt_eval,
            count_self_evolving=cnt_evo,
        )
