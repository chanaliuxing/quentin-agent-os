from __future__ import annotations
from dataclasses import dataclass
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta, UTC
from pathlib import Path
import json

from quentin.skills.schema import SkillSpec
from quentin.self_programming.schema import PatchProposal
from quentin.l3.research.experiments import ExperimentOrchestrator
from quentin.traces.core import JsonlTraceRecorder


@dataclass
class SkillPatchExperimentResult:
    experiment_id: str
    metrics_baseline: Dict[str, float]
    metrics_variant: Dict[str, float]
    metrics_delta: Dict[str, float]
    raw_result: Dict[str, Any]


def _load_eval_tasks_for_skill(
    skill: SkillSpec,
    repo_root: Path,
    days: int = 7,
    limit: int = 20,
) -> List[Dict[str, Any]]:
    """
    v1: 从 runtime trace 中抽一批该 domain 的任务，用来做 AB 实验。
    """
    path = repo_root / "data" / "traces"
    if not path.exists():
        return []

    since = datetime.now(UTC) - timedelta(days=days)
    tasks: List[Dict[str, Any]] = []

    for trace_file in path.glob("*.jsonl"):
        with trace_file.open("r", encoding="utf-8") as f:
            for line in f:
                try:
                    evt = json.loads(line)
                except json.JSONDecodeError:
                    continue

                if evt.get("event_type") != "TASK_PLANNED": # Assuming this event type
                    continue

                payload = evt.get("payload", {})
                if payload.get("domain") != skill.domain:
                    continue

                ts_str = evt.get("timestamp")
                if not ts_str:
                    continue
                ts = datetime.fromisoformat(ts_str)
                if ts < since:
                    continue

                task_spec = payload.get("task_spec")
                if not task_spec:
                    continue

                tasks.append(task_spec)
                if len(tasks) >= limit:
                    break
    return tasks

def build_skill_patch_experiment_config(
    skill: SkillSpec,
    patch: PatchProposal,
    repo_root: Path,
    days: int = 7,
    limit_tasks: int = 20,
) -> Optional[Dict[str, Any]]:
    """
    返回一个 ExperimentConfig dict，交给 ResearchAPI 使用。
    """
    tasks = _load_eval_tasks_for_skill(skill, repo_root, days=days, limit=limit_tasks)
    if not tasks:
        return None

    exp_config = {
        "name": f"skill_patch_eval::{skill.domain}::{skill.name}::{patch.proposal_id}",
        "description": f"A/B test for skill '{skill.name}' with patch {patch.proposal_id}",
        "variants": ["baseline", "variant"],
        "tasks": tasks,
        "meta": {
            "patch_id": patch.proposal_id,
            "skill_id": skill.id,
            "domain": skill.domain,
        },
    }
    return exp_config


def run_skill_patch_experiment(
    skill: SkillSpec,
    patch: PatchProposal,
    repo_root: Path,
    exp_orchestrator: ExperimentOrchestrator,
    trace_recorder: JsonlTraceRecorder,
) -> Optional[SkillPatchExperimentResult]:
    """
    - 创建/提交一个实验配置
    - 运行实验（同步/异步看你 ResearchAPI 的实现）
    - 收集 baseline 与 variant 的 metrics，并算 delta
    """
    config = build_skill_patch_experiment_config(skill, patch, repo_root)
    if not config:
        trace_recorder.record_event(
            event_type="skill_patch_experiment_no_tasks",
            payload={"skill_id": skill.id, "patch_id": patch.proposal_id},
        )
        return None

    trace_recorder.record_event(
        event_type="skill_patch_experiment_start",
        payload={
            "skill_id": skill.id,
            "patch_id": patch.proposal_id,
            "exp_name": config["name"],
        },
    )

    # v1：假设 ExperimentOrchestrator 有一个 run_experiment(config) 接口，返回 dict
    # The current implementation of run_experiment takes an experiment_id, not a config dict.
    # I will first create the experiment, then run it.
    
    exp_record = exp_orchestrator.create_experiment(**config)
    raw_result = exp_orchestrator.run_experiment(exp_record.config.experiment_id)

    exp_id = raw_result.experiment_id
    v_baseline = raw_result.variant_reports.get("baseline")
    v_variant = raw_result.variant_reports.get("variant")

    m_base = v_baseline.summary.to_dict() if v_baseline else {}
    m_var = v_variant.summary.to_dict() if v_variant else {}
    
    metrics_delta: Dict[str, float] = {}
    for k, base_val in m_base.items():
        if isinstance(base_val, (int, float)):
            var_val = m_var.get(k)
            if isinstance(var_val, (int, float)):
                metrics_delta[k] = var_val - base_val

    result = SkillPatchExperimentResult(
        experiment_id=exp_id,
        metrics_baseline=m_base,
        metrics_variant=m_var,
        metrics_delta=metrics_delta,
        raw_result=raw_result.to_dict(),
    )

    trace_recorder.record_event(
        event_type="skill_patch_experiment_done",
        payload={
            "skill_id": skill.id,
            "patch_id": patch.proposal_id,
            "experiment_id": exp_id,
            "metrics_baseline": m_base,
            "metrics_variant": m_var,
            "metrics_delta": metrics_delta,
        },
    )

    return result
