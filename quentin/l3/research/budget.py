from __future__ import annotations

from typing import List, Optional

from quentin.l3.research.experiments import ExperimentRecord
from quentin.l3.research.schemas import ResearchCycleRequest, ResearchBudgetConfig

class BudgetController:
    """
    负责控制研究预算。

    - 限制每个周期的实验数量
    - 以后可以扩展为控制 Token / 算力 / 资金消耗
    """

    def __init__(self, config: ResearchBudgetConfig) -> None:
        self.config = config

    def can_run_experiment(self, record: ExperimentRecord) -> bool:
        """
        判断单个实验是否在预算内（例如，是否已运行太多次）。
        """
        if self.config.max_runs_per_experiment is not None:
            if len(record.runs) >= self.config.max_runs_per_experiment:
                return False
        return True

    def limit_experiments_for_cycle(
        self,
        *,
        candidates: List[ExperimentRecord],
        request: ResearchCycleRequest,
    ) -> List[ExperimentRecord]:
        """
        根据预算，从候选实验列表中筛选出本周期可以运行的实验。
        """
        # 1. Filter out experiments that cannot be run
        runnable_candidates = [
            cand for cand in candidates if self.can_run_experiment(cand)
        ]

        # 2. Limit by number of experiments
        if self.config.max_experiments_per_cycle is None and request.max_experiments is None:
            return runnable_candidates

        limit = self.config.max_experiments_per_cycle if self.config.max_experiments_per_cycle is not None else request.max_experiments
        if request.max_experiments is not None and limit is not None:
            limit = min(limit, request.max_experiments)
        if limit is None:
            return runnable_candidates
        return runnable_candidates[:limit]
