# meta_agent/evolution/gap_quality_inspector.py
from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
import json

from meta_agent.llm.cli_clients import CLIModelClient, make_codex_cli_client, make_gemini_cli_client
from meta_agent.research.tool import ResearchTool, ResearchResult
from quentin.traces.core import JsonlTraceRecorder

trace = JsonlTraceRecorder(repo_root=".")

@dataclass
class GapQualityScore:
    clarity: float = 0.0
    feasibility: float = 0.0
    alignment: float = 0.0
    research_depth: float = 0.0
    priority: float = 0.0

@dataclass
class GapQualityReport:
    gap_id: str
    title: str
    raw_gap: Dict[str, Any]
    scores: GapQualityScore
    issues: List[str] = field(default_factory=list)
    suggestions: List[str] = field(default_factory=list)
    blueprint_patch_suggestion: Optional[str] = None

class GapQualityInspector:
    def __init__(
        self,
        codex: Optional[CliLLMClient] = None,
        gemini: Optional[CliLLMClient] = None,
        research_tool: Optional[ResearchTool] = None,
    ) -> None:
        self.codex = codex or make_codex_cli_client()
        self.gemini = gemini or make_gemini_cli_client()
        self.research_tool = research_tool or ResearchTool()

    def evaluate_gaps(self, gaps: List[Any], with_research: bool = True) -> List[GapQualityReport]:
        reports: List[GapQualityReport] = []
        for gap in gaps:
            gap_desc = {
                "id": getattr(gap, "id", None), "title": getattr(gap, "title", ""),
                "description": getattr(gap, "description", ""), "category": getattr(gap, "category", "")
            }
            trace.log_event(event_type="gap_quality_start", payload={"gap": gap_desc})
            research = self.research_tool.research_gap(gap) if with_research else None
            report = self._evaluate_single_gap(gap_desc, research)
            reports.append(report)
            trace.log_event(event_type="gap_quality_done", payload={"gap_id": gap_desc.get("id"), "scores": report.scores.__dict__})
        return reports

    def _evaluate_single_gap(self, gap_desc: Dict[str, Any], research: Optional[ResearchResult]) -> GapQualityReport:
        research_summary = research.merged_summary if research else "No external research was conducted."
        prompt = f"""
Analyze the quality of the following blueprint gap.
# Gap Description
{json.dumps(gap_desc, indent=2)}

# Research Summary
{research_summary}

# Task
Rate the gap on a scale of 0.0 to 1.0 for the following criteria: clarity, feasibility, alignment, research_depth, priority.
Also provide a list of issues, suggestions, and an optional rewrite of the blueprint clause (blueprint_patch_suggestion).
Output a single JSON object with keys: "scores", "issues", "suggestions", "blueprint_patch_suggestion".
The "scores" value should be an object with the 5 criteria.
"""
        data = self.gemini.generate_json(system="You are a blueprint quality inspector.", user=prompt)
        
        scores_raw = data.get("scores", {})
        score = GapQualityScore(
            clarity=float(scores_raw.get("clarity", 0.0)),
            feasibility=float(scores_raw.get("feasibility", 0.0)),
            alignment=float(scores_raw.get("alignment", 0.0)),
            research_depth=float(scores_raw.get("research_depth", 0.0)),
            priority=float(scores_raw.get("priority", 0.0)),
        )
        
        return GapQualityReport(
            gap_id=str(gap_desc.get("id")), title=gap_desc.get("title", ""), raw_gap=gap_desc,
            scores=score, issues=data.get("issues", []), suggestions=data.get("suggestions", []),
            blueprint_patch_suggestion=data.get("blueprint_patch_suggestion")
        )
