# meta_agent/observability/snapshot.py
from __future__ import annotations
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional

@dataclass
class LoopStatus: # ...
    name: str; runs_today: int; last_run_at: Optional[str]
    next_earliest_run_at: Optional[str]; max_runs_per_day: int

@dataclass
class PatchStats: # ...
    total_patches: int = 0; applied_patches: int = 0; rejected_patches: int = 0
    pending_patches: int = 0; last_24h_new: int = 0; last_24h_applied: int = 0
    last_24h_rejected: int = 0

@dataclass
class SkillStats: # ...
    total_skills: int = 0; avg_success_rate: float = 0.0; active_avg_success_rate: float = 0.0
    by_status: Dict[str, int] = field(default_factory=dict)
    top_recent_skills: List[Dict] = field(default_factory=list)

@dataclass
class GapStats: # ...
    total_gaps: int = 0; open_gaps: int = 0; closed_gaps: int = 0
    avg_clarity: Optional[float] = None; avg_alignment: Optional[float] = None
    low_quality_count: int = 0

@dataclass
class ResearchStats: # ...
    total_research_calls: int = 0; last_24h_research_calls: int = 0
    by_source: Dict[str, int] = field(default_factory=dict)
    last_research_at: Optional[str] = None

@dataclass
class BlueprintStats: # ...
    total_versions: int = 0; last_7d_versions: int = 0
    by_risk_level: Dict[str, int] = field(default_factory=dict)
    last_version_id: Optional[str] = None; last_version_at: Optional[str] = None
    last_version_summary: Optional[str] = None

@dataclass
class BlueprintEffectStats:
    total_analyzed: int = 0
    beneficial: int = 0
    neutral: int = 0
    harmful: int = 0
    unknown: int = 0
    last_beneficial_version_id: Optional[str] = None
    last_beneficial_at: Optional[str] = None
    last_harmful_version_id: Optional[str] = None
    last_harmful_at: Optional[str] = None

@dataclass
class SystemSnapshot:
    loops: List[LoopStatus]
    patches: PatchStats
    skills: SkillStats
    gaps: GapStats
    research: ResearchStats
    blueprint: BlueprintStats
    blueprint_effects: BlueprintEffectStats   # New field

    # Blueprint coverage analyzer inputs (flat maps keyed by section_id).
    blueprint_impl_status: Dict[str, Any] = field(default_factory=dict)
    blueprint_gaps: Dict[str, Any] = field(default_factory=dict)
    blueprint_skills: Dict[str, Any] = field(default_factory=dict)
    blueprint_tests: Dict[str, Any] = field(default_factory=dict)
    blueprint_self_evo: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict:
        return asdict(self)
