from __future__ import annotations

from dataclasses import asdict, is_dataclass
from typing import Any, Dict, List, Optional
import logging

from quentin.evolution.skill_loop import SkillEvolutionLoop

logger = logging.getLogger(__name__)


def _trace_to_dict(t: Any) -> Dict[str, Any]:
    """
    兼容：
    - ExecutionTrace dataclass
    - dict
    - 其它对象（作为 raw 包一层）
    """
    if isinstance(t, dict):
        return t
    if is_dataclass(t):
        return asdict(t)
    return {"raw": t}


class SleepLoop:
    """
    睡眠循环（Sleep / Consolidation Loop）v1 实现。

    职责：
      1. 聚合最近一段时间的 ExecutionTrace
      2. 统计成功 / 失败等概况
      3. 为 MemoryFabric 准备“巩固候选”（先以摘要形式给出）
      4. 触发 MemoryFabric 维护循环（promotion / decay）
      5. 调用 SkillEvolutionLoop（成功 Trace + issues）做技能/代码进化

    这里刻意保持“研究友好”：
      - 不强绑定任何具体 MemoryFabric API，只是约定性地调用 consolidate_from_traces() / run_maintenance_cycle()
      - 所有输入输出都是结构化 dict，方便以后接不同算法
    """

    def __init__(
        self,
        *,
        memory_fabric: Optional[Any] = None,
        skill_evolution_loop: Optional[SkillEvolutionLoop] = None,
        max_traces: int = 500,
        # Adding missing arguments from previous implementation to avoid breaking existing calls
        repo_root: Optional[Any] = None,
        trace_store: Optional[Any] = None,
        self_programming_engine: Optional[Any] = None,
        evolution_loop: Optional[Any] = None,
    ) -> None:
        self.memory_fabric = memory_fabric
        self.skill_evolution_loop = skill_evolution_loop or evolution_loop
        self.max_traces = max_traces
        self.trace_store = trace_store

    def run_once(
        self,
        *,
        recent_traces: Optional[List[Any]] = None,
        traces: Optional[List[Any]] = None,
        issues_from_immune: Optional[List[Dict[str, Any]]] = None,
        extra_context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        由 RuntimeFacade 调用：

        - recent_traces: 最近一段时间的 ExecutionTrace 列表（新在前或新在后均可）
        - issues_from_immune: 来自 ImmuneLoop 的问题列表（可为空）
        - extra_context: 额外信息（如运行批次 ID 等）

        返回：
        {
          "trace_stats": {...},
          "memory_consolidation": {...},
          "memory_maintenance": {...},
          "skill_evolution": {...},
        }
        """
        # Handle aliasing
        actual_traces = recent_traces or traces
        
        # If no traces provided but we have a trace_store, try to load them
        if actual_traces is None and self.trace_store:
            actual_traces = self.trace_store.load_recent(limit=self.max_traces)
        
        actual_traces = actual_traces or []

        ctx = extra_context or {}
        issues = issues_from_immune or []

        # 1) 预处理 trace（截断到 max_traces）
        if len(actual_traces) > self.max_traces:
            # 假设 recent_traces 是按时间排序的：我们保留最新的 max_traces
            actual_traces = actual_traces[-self.max_traces :]

        trace_dicts = [_trace_to_dict(t) for t in actual_traces]

        # 2) 统计成功 / 失败 / error 概况
        stats = self._summarize_traces(trace_dicts)

        # 3) MemoryFabric 巩固
        mem_consolidation: Dict[str, Any] = {}
        mem_maintenance: Dict[str, Any] = {}
        if self.memory_fabric is not None and hasattr(self.memory_fabric, "consolidate_from_traces"):
            try:
                mem_consolidation = self.memory_fabric.consolidate_from_traces(
                    trace_dicts,
                    context={"source": "sleep_loop", **ctx},
                )
            except Exception:
                logger.exception("SleepLoop: memory_fabric.consolidate_from_traces failed")
                mem_consolidation = {"status": "error"}

            # 4) MemoryFabric 维护循环（promotion / decay）
            if hasattr(self.memory_fabric, "run_maintenance_cycle"):
                try:
                    mem_maintenance = self.memory_fabric.run_maintenance_cycle(
                        config={"source": "sleep_loop"},
                    )
                except Exception:
                    logger.exception("SleepLoop: memory_fabric.run_maintenance_cycle failed")
                    mem_maintenance = {"status": "error"}

        # 5) Skill & Code Evolution（如果有）
        se_result: Dict[str, Any] = {}
        if self.skill_evolution_loop is not None:
            successful = [t for t in trace_dicts if t.get("status") == "success"]
            try:
                se_result = self.skill_evolution_loop.run_once(
                    successful_traces=successful,
                    issues=issues,
                    test_suites=["unit", "static_analysis"],
                    extra_context={"source": "sleep_loop", **ctx},
                )
            except Exception:
                logger.exception("SleepLoop: skill_evolution_loop.run_once failed")
                se_result = {"status": "error"}

        return {
            "trace_stats": stats,
            "memory_consolidation": mem_consolidation,
            "memory_maintenance": mem_maintenance,
            "skill_evolution": se_result,
        }

    # --------------------------------------------------
    # 内部：Trace 概况统计
    # --------------------------------------------------
    def _summarize_traces(self, traces: List[Dict[str, Any]]) -> Dict[str, Any]:
        total = len(traces)
        success = sum(1 for t in traces if t.get("status") == "success")
        failed = sum(1 for t in traces if t.get("status") == "failed")
        error = sum(1 for t in traces if t.get("status") == "error")
        unknown = total - success - failed - error

        domains: Dict[str, int] = {}
        for t in traces:
            d = t.get("domain", "unknown")
            domains[d] = domains.get(d, 0) + 1

        return {
            "total_traces": total,
            "success": success,
            "failed": failed,
            "error": error,
            "unknown": unknown,
            "by_domain": domains,
        }
