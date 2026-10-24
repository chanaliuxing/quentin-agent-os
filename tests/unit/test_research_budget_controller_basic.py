from __future__ import annotations

from dataclasses import dataclass

from quentin.l3.research.budget import BudgetController
from quentin.l3.research.schemas import ResearchBudgetConfig, ResearchCycleRequest


@dataclass
class _DummyExperiment:
    runs: list


def test_budget_controller_limits_experiments_per_cycle():
    ctl = BudgetController(config=ResearchBudgetConfig(max_experiments_per_cycle=2))
    req = ResearchCycleRequest(max_experiments=None)

    candidates = [_DummyExperiment(runs=[]) for _ in range(5)]
    out = ctl.limit_experiments_for_cycle(candidates=candidates, request=req)
    assert len(out) == 2

