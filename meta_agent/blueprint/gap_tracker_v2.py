# meta_agent/blueprint/gap_tracker_v2.py
from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
import json
from pathlib import Path
import yaml

from meta_agent.blueprint.gap_quality import (
    GapQualityEvaluator,
    GapContext,
    GapQualityScore,
)
from meta_agent.monitoring.status_snapshot import build_status_snapshot
from quentin.traces.core import JsonlTraceRecorder

trace = JsonlTraceRecorder(repo_root=".")

@dataclass
class BlueprintGap:
    id: str
    title: str
    description: str
    category: str
    priority: int
    status: str
    related_files: List[str] = field(default_factory=list)
    blueprint_clause: Optional[Dict[str, Any]] = None
    quality: Optional[GapQualityScore] = None

    def to_gap_like(self) -> "GapLike":
        from meta_agent.self_programming.engine_v2 import GapLike
        return GapLike(
            id=self.id, title=self.title, description=self.description,
            category=self.category, priority=self.priority, related_files=self.related_files
        )

class BlueprintGapTrackerV2:
    def __init__(self, blueprint_path: str | Path = "blueprint/blueprint_v2.yml", project_root: str | Path = "."):
        self.blueprint_path = Path(blueprint_path)
        self.project_root = Path(project_root)
        self._quality_evaluator = GapQualityEvaluator()

    def collect_all_gaps(self, with_quality: bool = True) -> List[BlueprintGap]:
        blueprint = self._load_blueprint()
        initial_gaps = self._derive_gaps_from_blueprint(blueprint)

        if not with_quality:
            return initial_gaps

        snapshot = build_status_snapshot(window_hours=24)
        enriched: List[BlueprintGap] = []
        for g in initial_gaps:
            if not g.related_files:
                enriched.append(g)
                continue
            
            gap_ctx = GapContext(
                id=g.id, title=g.title, description=g.description, category=g.category,
                priority=g.priority, blueprint_clause=g.blueprint_clause, related_files=g.related_files
            )
            score = self._quality_evaluator.evaluate_gap(gap_ctx, snapshot=snapshot)
            g.quality = score
            enriched.append(g)

        self._dump_gap_snapshot(enriched)
        return enriched

    def find_top_gaps(self, limit: int = 5, min_priority: int = 1) -> List[BlueprintGap]:
        gaps = self.collect_all_gaps(with_quality=True)
        def score_gap(g: BlueprintGap) -> float:
            base = g.priority
            q = g.quality.overall_score if g.quality else 5.0
            return (base * 2.0) - q
        
        filtered = [g for g in gaps if g.priority >= min_priority]
        sorted_gaps = sorted(filtered, key=score_gap, reverse=True)
        top = sorted_gaps[:limit]
        # Use a standard TraceEventType so recorder doesn't warn on unknown event_type strings.
        trace.record_event(
            event_type="decision",
            trace_id="gap_tracker_v2",
            payload={"action": "gap_tracker_top_gaps", "limit": limit, "top_gap_ids": [g.id for g in top]},
        )
        return top

    def _load_blueprint(self) -> Dict[str, Any]:
        if not self.blueprint_path.exists():
            raise FileNotFoundError(f"Blueprint not found: {self.blueprint_path}")
        text = self.blueprint_path.read_text(encoding="utf-8")
        return yaml.safe_load(text)

    def _derive_gaps_from_blueprint(self, blueprint: Dict[str, Any]) -> List[BlueprintGap]:
        # Heuristic extraction from `blueprint_v2.yml` clauses.
        gaps: List[BlueprintGap] = []
        for section in blueprint.get("sections", []):
            for clause in section.get("clauses", []):
                gaps.append(BlueprintGap(
                    id=clause.get("id", ""),
                    title=clause.get("title", ""),
                    description=clause.get("rationale", ""),
                    category=clause.get("category", "misc"),
                    priority=int(clause.get("priority", 1)),
                    status=clause.get("status", "planned"),
                    related_files=clause.get("impl_refs", []), # Assumes impl_refs in YAML
                    blueprint_clause=clause,
                ))
        return gaps

    def _dump_gap_snapshot(self, gaps: List[BlueprintGap]) -> None:
        out_path = Path("data/blueprint/gap_quality_snapshot.json")
        out_path.parent.mkdir(parents=True, exist_ok=True)
        serializable = [{
            "id": g.id, "title": g.title, "category": g.category, "priority": g.priority, "status": g.status,
            "related_files": g.related_files, "quality": g.quality.to_dict() if g.quality else None
        } for g in gaps]
        out_path.write_text(json.dumps(serializable, ensure_ascii=False, indent=2), encoding="utf-8")
