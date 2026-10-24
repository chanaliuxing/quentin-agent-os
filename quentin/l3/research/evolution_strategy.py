from __future__ import annotations

from typing import List, Optional

from quentin.l3.research.experiments import ExperimentRecord


class EvolutionStrategyManager:
    """
    负责决定“下一步应该在哪些实验上投入资源”的策略模块。

    可以实现多种策略：
      - simple: 按最新修改时间排序
      - success_rate_desc: 按成功率降序
      - uncertainty_sampling: 选择最不确定的（例如，运行次数少、结果方差大）
      - etc.
    """

    def __init__(self, *, default_strategy: str = "simple") -> None:
        self.default_strategy = default_strategy

    def select_experiments_for_cycle(
        self,
        *,
        experiments: List[ExperimentRecord],
        strategy: Optional[str] = None,
    ) -> List[ExperimentRecord]:
        """
        根据指定策略，对候选实验列表进行排序和筛选。
        """
        selected_strategy = strategy or self.default_strategy

        if selected_strategy == "simple":
            # 按最近一次运行时间排序（如果没有运行过，就按创建时间）
            return sorted(
                experiments,
                key=lambda r: r.runs[-1].finished_at if r.runs else 0,
                reverse=True,
            )
        elif selected_strategy == "success_rate_desc":
            # 按最近一次运行的成功率降序排序
            return sorted(
                experiments,
                key=lambda r: r.runs[-1].variant_reports[r.config.variants[0]].summary.success_rate if r.runs and r.config.variants else 0,
                reverse=True,
            )
        else:
            # 默认返回原始列表
            return experiments