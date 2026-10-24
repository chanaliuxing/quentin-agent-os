# meta_agent/monitoring/status_snapshot.py
from __future__ import annotations
from quentin.utils.time import now_iso, now_utc
from dataclasses import dataclass, asdict, field
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from pathlib import Path
import json

from meta_agent.skills.registry import SkillRegistry, SkillStatus
from quentin.traces.core import JsonlTraceRecorder  # 仅用于一致日志，如需


@dataclass
class TaskStats:
    total: int = 0
    success: int = 0
    fail: int = 0

    @property
    def success_rate(self) -> float:
        if self.total == 0:
            return 0.0
        return self.success / self.total

    @property
    def fail_rate(self) -> float:
        if self.total == 0:
            return 0.0
        return self.fail / self.total


@dataclass
class OrchestratorTaskStats:
    runs: int = 0
    errors: int = 0


@dataclass
class SkillStats:
    total: int
    by_status: Dict[str, int]
    by_domain: Dict[str, Dict[str, int]]  # domain -> {status -> count}


@dataclass
class PatchStats:
    total_evaluated: int
    pass_count: int
    fail_count: int
    needs_review_count: int


@dataclass
class ExperimentStats:
    total: int
    last_experiment_ids: List[str]


@dataclass
class BlueprintStats:
    """
    新增：蓝图统计
    """
    implemented_clauses: int = 0
    unstable_clauses: int = 0
    completion_by_category: Dict[str, float] = field(default_factory=dict)


@dataclass
class StatusSnapshot:
    generated_at: str
    window_hours: int

    # 任务层面
    task_stats_overall: TaskStats
    task_stats_by_domain: Dict[str, TaskStats]

    # 调度层面
    orchestrator_tasks: Dict[str, OrchestratorTaskStats]

    # Skill 层面
    skills: SkillStats

    # Patch & 实验层面
    patches: PatchStats
    experiments: ExperimentStats

    # 蓝图层面
    blueprint_stats: BlueprintStats

    # 其他你想补充的 summary
    extra: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        # dataclass 里嵌套 dataclass 手动处理一下
        def _ts_to_dict(ts: TaskStats) -> Dict[str, Any]:
            return {
                "total": ts.total,
                "success": ts.success,
                "fail": ts.fail,
                "success_rate": ts.success_rate,
                "fail_rate": ts.fail_rate,
            }

        def _ots_to_dict(ots: OrchestratorTaskStats) -> Dict[str, Any]:
            return {
                "runs": ots.runs,
                "errors": ots.errors,
            }

        return {
            "generated_at": self.generated_at,
            "window_hours": self.window_hours,
            "task_stats_overall": _ts_to_dict(self.task_stats_overall),
            "task_stats_by_domain": {
                d: _ts_to_dict(ts) for d, ts in self.task_stats_by_domain.items()
            },
            "orchestrator_tasks": {
                name: _ots_to_dict(stat)
                for name, stat in self.orchestrator_tasks.items()
            },
            "skills": {
                "total": self.skills.total,
                "by_status": self.skills.by_status,
                "by_domain": self.skills.by_domain,
            },
            "patches": {
                "total_evaluated": self.patches.total_evaluated,
                "pass_count": self.patches.pass_count,
                "fail_count": self.patches.fail_count,
                "needs_review_count": self.patches.needs_review_count,
            },
            "experiments": {
                "total": self.experiments.total,
                "last_experiment_ids": self.experiments.last_experiment_ids,
            },
            "blueprint_stats": {
                "implemented_clauses": self.blueprint_stats.implemented_clauses,
                "unstable_clauses": self.blueprint_stats.unstable_clauses,
                "completion_by_category": self.blueprint_stats.completion_by_category,
            },
            "extra": self.extra,
        }


from meta_agent.monitoring.aggregators import (
    aggregate_task_stats,
    aggregate_orchestrator_stats,
    aggregate_skill_stats,
    aggregate_patch_stats,
    aggregate_experiment_stats,
    aggregate_blueprint_stats,
)


def build_status_snapshot(window_hours: int = 24) -> StatusSnapshot:
    # 1) 任务统计
    overall_ts, by_domain_ts = aggregate_task_stats(window_hours=window_hours)

    # 2) orchestrator 调度统计
    orch_stats = aggregate_orchestrator_stats(window_hours=window_hours)

    # 3) skills
    skill_stats = aggregate_skill_stats()

    # 4) patches
    patch_stats = aggregate_patch_stats(window_hours=window_hours)

    # 5) experiments
    exp_stats = aggregate_experiment_stats(window_hours=window_hours)
    
    # 6) blueprint
    blueprint_stats = aggregate_blueprint_stats()

    snapshot = StatusSnapshot(
        generated_at=now_iso(),
        window_hours=window_hours,
        task_stats_overall=overall_ts,
        task_stats_by_domain=by_domain_ts,
        orchestrator_tasks=orch_stats,
        skills=skill_stats,
        patches=patch_stats,
        experiments=exp_stats,
        blueprint_stats=blueprint_stats,
        extra={},  # 未来可以塞更多 summary，比如 memory 命中率
    )
    return snapshot


def write_status_snapshot(
    output_path: str | Path = "data/status_snapshot.json",
    window_hours: int = 24,
) -> StatusSnapshot:
    snapshot = build_status_snapshot(window_hours=window_hours)
    data = snapshot.to_dict()

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    return snapshot
