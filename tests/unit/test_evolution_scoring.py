from dataclasses import dataclass

from quentin.l3.research.evolution import EvolutionScoreWeights, EvolutionStrategyManager
from quentin.self_improvement.schemas import ImprovementTask


@dataclass
class _StubGap:
    capability_id: str
    requirement_id: str
    priority: int = 1
    spec_status: str = "missing"
    severity: str = "high"
    meta: dict | None = None


class _StubTracker:
    def __init__(self, gaps):
        self._gaps = gaps

    def scan(self):
        return self._gaps


class _StubResearch:
    def __init__(self, stats_map):
        self._stats_map = stats_map

    def get_task_level_stats(self, capability, requirement_id):
        return self._stats_map.get((capability, requirement_id), {})


def test_evolution_scoring_prefers_higher_success_and_lower_cost():
    gaps = [_StubGap(capability_id="capA", requirement_id="req1", priority=2)]
    stats = {
        ("capA", "req1"): {"success_rate": 0.9, "avg_latency_sec": 1.0, "avg_cost": 0.2},
        ("capB", "req2"): {"success_rate": 0.6, "avg_latency_sec": 1.0, "avg_cost": 0.6},
    }
    manager = EvolutionStrategyManager(
        blueprint_tracker=_StubTracker(gaps),
        research_manager=_StubResearch(stats),
    )

    tasks = [
        ImprovementTask(task_id="t1", capability="capA", requirement_id="req1", overall_status="missing"),
        ImprovementTask(task_id="t2", capability="capB", requirement_id="req2", overall_status="missing"),
    ]
    manager.si_manager.list_tasks = lambda: tasks

    ranked = manager.suggest_next_tasks(limit=2)
    assert [t.task_id for t, _ in ranked][0] == "t1"


def test_evolution_scoring_weight_override():
    stats = {
        ("capA", "req1"): {"success_rate": 0.6, "avg_latency_sec": 3.0, "avg_cost": 0.1},
        ("capB", "req2"): {"success_rate": 0.55, "avg_latency_sec": 0.5, "avg_cost": 0.05},
    }
    weights = EvolutionScoreWeights(success=0.2, latency=-2.0, cost=-3.0)
    manager = EvolutionStrategyManager(
        blueprint_tracker=_StubTracker([]),
        research_manager=_StubResearch(stats),
        score_weights=weights,
    )
    tasks = [
        ImprovementTask(task_id="t1", capability="capA", requirement_id="req1", overall_status="missing"),
        ImprovementTask(task_id="t2", capability="capB", requirement_id="req2", overall_status="missing"),
    ]
    manager.si_manager.list_tasks = lambda: tasks

    ranked = manager.suggest_next_tasks(limit=2)
    assert [t.task_id for t, _ in ranked][0] == "t2"
