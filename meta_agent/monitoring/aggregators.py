# meta_agent/monitoring/aggregators.py
from __future__ import annotations
from quentin.utils.time import now_iso, now_utc, normalize_to_utc_iso
from typing import Dict, Any, List, Tuple
from datetime import datetime, timedelta
from pathlib import Path
import json
import yaml

from meta_agent.monitoring.status_snapshot import (
    TaskStats,
    OrchestratorTaskStats,
    SkillStats,
    PatchStats,
    ExperimentStats,
    BlueprintStats,
)
from meta_agent.skills.registry import SkillRegistry, SkillStatus
from meta_agent.blueprint.model import BlueprintDocument
from meta_agent.blueprint.gap_tracker import BlueprintGapTrackerV2


def _iter_events(path: Path, since: datetime | None = None):
    if not path.exists():
        return
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                evt = json.loads(line)
            except json.JSONDecodeError:
                continue

            ts_str = (
                evt.get("ts")
                or evt.get("timestamp")
                or evt.get("payload", {}).get("ts")
            )
            if not ts_str:
                yield evt
                continue

            try:
                ts = datetime.fromisoformat(normalize_to_utc_iso(ts_str))
            except Exception:
                yield evt
                continue

            if since is not None and ts < since:
                continue
            yield evt


# -------- 1. 任务统计 --------

def aggregate_task_stats(
    runtime_log_path: str | Path = "logs/runtime_events.jsonl",
    window_hours: int = 24,
) -> tuple[TaskStats, Dict[str, TaskStats]]:
    """
    根据 runtime_events.jsonl 统计：
    - 总任务量 / 成功 / 失败
    - 按 domain 维度的 TaskStats
    假设 event_type="task_done"，payload 中有：
    {
      "domain": "...",
      "success": bool
    }
    """
    path = Path(runtime_log_path)
    since = now_utc() - timedelta(hours=window_hours)

    overall = TaskStats()
    by_domain: Dict[str, TaskStats] = {}

    for evt in _iter_events(path, since=since):
        if evt.get("event_type") != "task_done":
            continue
        payload = evt.get("payload", {})
        domain = payload.get("domain", "unknown")
        success = bool(payload.get("success"))

        overall.total += 1
        if success:
            overall.success += 1
        else:
            overall.fail += 1

        stats = by_domain.setdefault(domain, TaskStats())
        stats.total += 1
        if success:
            stats.success += 1
        else:
            stats.fail += 1

    return overall, by_domain


# -------- 2. Orchestrator 调度统计 --------

def aggregate_orchestrator_stats(
    orchestrator_log_path: str | Path = "logs/orchestrator_daemon.jsonl",
    window_hours: int = 24,
) -> Dict[str, OrchestratorTaskStats]:
    """
    聚合 Orchestrator 的调度情况：
    - task_start / task_done / task_error
    """
    path = Path(orchestrator_log_path)
    since = now_utc() - timedelta(hours=window_hours)

    stats: Dict[str, OrchestratorTaskStats] = {}

    for evt in _iter_events(path, since=since):
        et = evt.get("event_type")
        payload = evt.get("payload", {})
        task_name = payload.get("task_name")
        if not task_name:
            continue

        rec = stats.setdefault(task_name, OrchestratorTaskStats())

        if et == "task_done":
            rec.runs += 1
        elif et == "task_error":
            rec.errors += 1

    return stats


# -------- 3. Skill 统计 --------

def aggregate_skill_stats(skill_registry: SkillRegistry | None = None) -> SkillStats:
    """
    直接从 SkillRegistry 中统计。
    """
    reg = skill_registry or SkillRegistry()
    all_skills = reg.list_skills()

    total = len(all_skills)
    by_status: Dict[str, int] = {}
    by_domain: Dict[str, Dict[str, int]] = {}

    for s in all_skills:
        status_key = s.status.value
        by_status[status_key] = by_status.get(status_key, 0) + 1

        dom_map = by_domain.setdefault(s.domain, {})
        dom_map[status_key] = dom_map.get(status_key, 0) + 1

    return SkillStats(
        total=total,
        by_status=by_status,
        by_domain=by_domain,
    )


# -------- 4. Patch / Skill Impl 流水线统计 --------

def aggregate_patch_stats(
    skill_impl_log_path: str | Path = "logs/skill_impl_runner.jsonl",
    window_hours: int = 24,
) -> PatchStats:
    """
    从 skill_impl_runner 日志中聚合 patch 的评估结果。
    """
    path = Path(skill_impl_log_path)
    since = now_utc() - timedelta(hours=window_hours)

    total = 0
    pass_count = 0
    fail_count = 0
    needs_review_count = 0

    for evt in _iter_events(path, since=since):
        if evt.get("event_type") != "skill_impl_evaluated":
            continue

        payload = evt.get("payload", {})
        status = (payload.get("status") or "").lower()
        total += 1

        if status == "pass":
            pass_count += 1
        elif status == "fail":
            fail_count += 1
        else:
            needs_review_count += 1

    return PatchStats(
        total_evaluated=total,
        pass_count=pass_count,
        fail_count=fail_count,
        needs_review_count=needs_review_count,
    )


# -------- 5. 实验统计 --------

def aggregate_experiment_stats(
    experiment_log_path: str | Path = "logs/skill_patch_experiments.jsonl",
    window_hours: int = 24,
    max_ids: int = 20,
) -> ExperimentStats:
    """
    从 skill_patch_experiments.jsonl 统计实验数量和最近一些 experiment_id。
    """
    path = Path(experiment_log_path)
    since = now_utc() - timedelta(hours=window_hours)

    total = 0
    last_ids: List[str] = []

    for evt in _iter_events(path, since=since):
        if evt.get("event_type") != "skill_patch_experiment_done":
            continue
        payload = evt.get("payload", {})
        exp_id = payload.get("experiment_id")
        if not exp_id:
            continue
        total += 1
        last_ids.append(exp_id)

    # 只保留最近 max_ids 个
    if len(last_ids) > max_ids:
        last_ids = last_ids[-max_ids:]

    return ExperimentStats(
        total=total,
        last_experiment_ids=last_ids,
    )

# -------- 6. 蓝图统计 (新增) --------

def aggregate_blueprint_stats() -> BlueprintStats:
    """
    从蓝图文件和 gap tracker 中聚合统计数据。
    """
    blueprint_path = Path("blueprint/blueprint_v2.yml")
    if not blueprint_path.exists():
        return BlueprintStats(implemented_clauses=0, unstable_clauses=0, completion_by_category={})

    try:
        data = yaml.safe_load(blueprint_path.read_text(encoding="utf-8")) or {}
    except Exception:
        return BlueprintStats(implemented_clauses=0, unstable_clauses=0, completion_by_category={})

    total = 0
    implemented = 0
    by_cat_total: Dict[str, int] = {}
    by_cat_impl: Dict[str, int] = {}

    for section in data.get("sections", []) if isinstance(data, dict) else []:
        for clause in section.get("clauses", []) if isinstance(section, dict) else []:
            total += 1
            cat = str(clause.get("category") or "other")
            by_cat_total[cat] = by_cat_total.get(cat, 0) + 1

            status = str(clause.get("status") or "planned").lower()
            if status == "implemented":
                implemented += 1
                by_cat_impl[cat] = by_cat_impl.get(cat, 0) + 1

    completion: Dict[str, float] = {}
    for cat, n in by_cat_total.items():
        completion[cat] = (by_cat_impl.get(cat, 0) / max(1, n))

    unstable = max(0, total - implemented)
    return BlueprintStats(
        implemented_clauses=int(implemented),
        unstable_clauses=int(unstable),
        completion_by_category=completion,
    )
