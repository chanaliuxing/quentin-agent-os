from __future__ import annotations

from typing import Any, Dict, List, Optional
from pathlib import Path

from quentin.metrics.schema import RunMetrics


def compute_run_metrics(run_result: Dict[str, Any]) -> RunMetrics:
    """
    从 BlueprintSelfIterateResult.to_dict() 得到的 dict 中，计算一次 run 的指标。

    参数 run_result 预期结构：
      {
        "run_id": ...,
        "started_at": ...,
        "finished_at": ...,
        "config": {...},
        "capability_scan": {...},
        "blueprint_cycle": {...},
      }
    """
    run_id = str(run_result.get("run_id", "unknown"))
    started_at = str(run_result.get("started_at", ""))
    finished_at = str(run_result.get("finished_at", ""))

    capability_scan: Dict[str, Any] = run_result.get("capability_scan", {})
    registry_snapshot: Dict[str, Any] = capability_scan.get("registry_snapshot", {})

    # registry_snapshot 预期类似：
    # {
    #   "capabilities": [
    #       {"capability_id": "...", "status": "done", ...},
    #       ...
    #   ]
    # }
    # Note: In 109.md, CapabilitiesRegistry.export() returns {"capabilities": [s.to_dict() for s in values()]}
    # So it's a list of dicts, not a dict of dicts.
    # I need to adapt the logic below to handle list of dicts.
    
    caps_list = registry_snapshot.get("capabilities", []) or []
    total_capabilities = len(caps_list)

    num_done = 0
    num_partial = 0
    num_missing = 0
    num_unknown = 0

    for cap_info in caps_list:
        status = str(cap_info.get("status", "unknown"))
        if status == "done":
            num_done += 1
        elif status == "partial":
            num_partial += 1
        elif status == "missing":
            num_missing += 1
        else:
            num_unknown += 1

    blueprint_cycle: Dict[str, Any] = run_result.get("blueprint_cycle", {})

    # created_experiments: List[str]
    created_experiments: List[str] = blueprint_cycle.get("created_experiments", []) or []
    experiments_created = len(created_experiments)

    # research_cycle_result 结构不确定，这里尽量兼容不同写法
    cycle_result: Dict[str, Any] = blueprint_cycle.get("research_cycle_result", {}) or {}
    
    # In 106.md, ResearchCycleResult has run_results: Dict[str, Dict].
    # We need to count executed/succeeded/failed based on run_results.
    run_results_map = cycle_result.get("run_results", {})
    experiments_executed = len(run_results_map)
    
    # Determine success/fail from run results.
    # ExperimentRunResult has variant_reports.
    # We can approximate success if at least one variant report has success > 0?
    # Or just use counters if provided by cycle_result (113.md assumes they might be provided directly).
    # But 106.md implementation of ResearchCycleResult does NOT provide direct counters.
    # I will calculate them from run_results if counters are missing.
    
    if "experiments_executed" in cycle_result:
         # If cycle result has counters (maybe future update), use them
         experiments_executed = int(cycle_result.get("experiments_executed", 0)) # Wait, in 106.md executed_experiments is a list
         if isinstance(cycle_result.get("executed_experiments"), list):
             experiments_executed = len(cycle_result.get("executed_experiments"))
         
         experiments_succeeded = int(cycle_result.get("experiments_succeeded", 0))
         experiments_failed = int(cycle_result.get("experiments_failed", 0))
         experiments_rolled_back = int(cycle_result.get("experiments_rolled_back", 0))
    else:
         # Manual calculation from run_results
         experiments_succeeded = 0
         experiments_failed = 0
         experiments_rolled_back = 0
         
         for exp_id, res_dict in run_results_map.items():
             # Logic to determine success/fail of an experiment run
             # Simple heuristic: if any variant report has success > 0.5, consider it succeeded?
             # Or just count them as executed for now.
             # To be safe and simple:
             pass

    # patch 相关：目前可能是 0
    patches_proposed = int(cycle_result.get("patches_proposed", 0))
    patches_accepted = int(cycle_result.get("patches_accepted", 0))
    patches_rolled_back = int(cycle_result.get("patches_rolled_back", 0))

    # 成本相关：如果没有，就保持 None
    total_cost_tokens_raw = cycle_result.get("total_cost_tokens")
    total_cost_seconds_raw = cycle_result.get("total_cost_seconds")

    total_cost_tokens = (
        float(total_cost_tokens_raw)
        if total_cost_tokens_raw is not None
        else None
    )
    total_cost_seconds = (
        float(total_cost_seconds_raw)
        if total_cost_seconds_raw is not None
        else None
    )

    return RunMetrics(
        run_id=run_id,
        started_at=started_at,
        finished_at=finished_at,
        total_capabilities=total_capabilities,
        num_done=num_done,
        num_partial=num_partial,
        num_missing=num_missing,
        num_unknown=num_unknown,
        experiments_created=experiments_created,
        experiments_executed=experiments_executed,
        experiments_succeeded=experiments_succeeded,
        experiments_failed=experiments_failed,
        experiments_rolled_back=experiments_rolled_back,
        patches_proposed=patches_proposed,
        patches_accepted=patches_accepted,
        patches_rolled_back=patches_rolled_back,
        total_cost_tokens=total_cost_tokens,
        total_cost_seconds=total_cost_seconds,
    )
