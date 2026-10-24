from __future__ import annotations
from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Optional


@dataclass
class ResearchBudgetConfig:
    # None 表示不设限（仅适用于本地模型场景）
    max_experiments_per_cycle: Optional[int] = None
    max_runtime_sec_per_experiment: Optional[float] = None
    max_runs_per_experiment: Optional[int] = None
    def to_dict(self) -> Dict[str, Any]: return asdict(self)

@dataclass
class ResearchCycleRequest:
    strategy: str = "simple"
    max_experiments: Optional[int] = None
    def to_dict(self) -> Dict[str, Any]: return asdict(self)

@dataclass
class ResearchCycleResult:
    started_at: float
    finished_at: float
    executed_experiments: List[str]
    run_results: Dict[str, Dict[str, Any]]
    variant_rankings: Dict[str, Dict[str, Any]]
    def to_dict(self) -> Dict[str, Any]: return asdict(self)


@dataclass
class PromotionDecision:
    """
    Research decision artifact for A/B -> promote.

    This is intentionally JSON-friendly and schema-stable.
    """

    decision_id: str
    experiment_id: str
    target_module: str
    metric: str
    winner_variant_id: str
    loser_variant_id: str
    metrics_delta: Dict[str, Any]
    promote_policy: Dict[str, Any]
    required_gates: List[str]
    allow_apply: bool
    reason: str
    created_at: float

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
