from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class VariantSlice:
    name: str
    total_runs: int
    acceptance_pass_rate: float
    terminal_distribution: dict[str, int]
    primary_failure_distribution: dict[str, int]
    top_primary_failures: list[tuple[str, int]]
    subprocess_nonzero_exit_count: int
    subprocess_nonzero_exit_stage_distribution: dict[str, int]
    subprocess_nonzero_exit_owner_distribution: dict[str, int]
    subprocess_nonzero_exit_action_distribution: dict[str, int]


def load_execution_summaries(evidence_root: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not evidence_root.exists():
        return rows
    for path in evidence_root.rglob("execution_summary.json"):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        payload["_path"] = str(path)
        payload["_mtime"] = path.stat().st_mtime
        rows.append(payload)
    return rows


def filter_variant_rows(
    *,
    rows: list[dict[str, Any]],
    variant_tag: str,
    match_mode: str = "prefix",
    window_size: int = 100,
) -> list[dict[str, Any]]:
    tag = str(variant_tag).strip()
    if not tag:
        return []
    mode = str(match_mode).strip().lower()
    matched: list[dict[str, Any]] = []
    for row in rows:
        workflow_id = str(row.get("workflow_id", "")).strip()
        if not workflow_id:
            continue
        if mode == "prefix" and workflow_id.startswith(tag):
            matched.append(row)
        if mode == "contains" and tag in workflow_id:
            matched.append(row)
        if mode == "exact" and workflow_id == tag:
            matched.append(row)
    matched.sort(key=lambda item: float(item.get("_mtime", 0.0)), reverse=True)
    return matched[: max(1, int(window_size))]


def summarize_variant(*, name: str, rows: list[dict[str, Any]]) -> VariantSlice:
    terminal_counter = Counter(
        str(item.get("terminal_state", "")).strip().upper()
        for item in rows
        if str(item.get("terminal_state", "")).strip()
    )
    primary_counter = Counter(
        str(item.get("primary_failure_type", "")).strip().upper()
        for item in rows
        if str(item.get("primary_failure_type", "")).strip()
    )
    passed = sum(1 for item in rows if str(item.get("acceptance_status", "")).strip().lower() == "passed")
    total = len(rows)
    nonzero_rows = [
        item for item in rows if str(item.get("primary_failure_type", "")).strip().upper() == "AGENT_SUBPROCESS_NONZERO_EXIT"
    ]
    stage_counter = Counter()
    owner_counter = Counter()
    action_counter = Counter()
    for row in nonzero_rows:
        stage = _extract_subprocess_stage(row)
        owner, action = _owner_action_for_stage(stage)
        stage_counter[stage] += 1
        owner_counter[owner] += 1
        action_counter[action] += 1
    return VariantSlice(
        name=name,
        total_runs=total,
        acceptance_pass_rate=round(passed / total, 4) if total else 0.0,
        terminal_distribution=dict(terminal_counter),
        primary_failure_distribution=dict(primary_counter),
        top_primary_failures=primary_counter.most_common(10),
        subprocess_nonzero_exit_count=len(nonzero_rows),
        subprocess_nonzero_exit_stage_distribution=dict(stage_counter),
        subprocess_nonzero_exit_owner_distribution=dict(owner_counter),
        subprocess_nonzero_exit_action_distribution=dict(action_counter),
    )


def to_markdown(*, slice_a: VariantSlice, slice_b: VariantSlice) -> str:
    lines = [
        f"# Variant Compare: `{slice_a.name}` vs `{slice_b.name}`",
        "",
        "## Summary",
        f"- `{slice_a.name}` total_runs: `{slice_a.total_runs}`, acceptance_pass_rate: `{slice_a.acceptance_pass_rate}`",
        f"- `{slice_b.name}` total_runs: `{slice_b.total_runs}`, acceptance_pass_rate: `{slice_b.acceptance_pass_rate}`",
        f"- pass_rate_delta (`{slice_b.name}` - `{slice_a.name}`): `{round(slice_b.acceptance_pass_rate - slice_a.acceptance_pass_rate, 4)}`",
        "",
        "## Terminal Distribution",
        f"- `{slice_a.name}`: `{slice_a.terminal_distribution}`",
        f"- `{slice_b.name}`: `{slice_b.terminal_distribution}`",
        "",
        "## Primary Failure Distribution",
        f"- `{slice_a.name}`: `{slice_a.primary_failure_distribution}`",
        f"- `{slice_b.name}`: `{slice_b.primary_failure_distribution}`",
        "",
        "## Top Primary Failures",
        f"- `{slice_a.name}`: `{slice_a.top_primary_failures}`",
        f"- `{slice_b.name}`: `{slice_b.top_primary_failures}`",
        "",
        "## AGENT_SUBPROCESS_NONZERO_EXIT Breakdown",
        f"- `{slice_a.name}` count: `{slice_a.subprocess_nonzero_exit_count}`",
        f"- `{slice_a.name}` stages: `{slice_a.subprocess_nonzero_exit_stage_distribution}`",
        f"- `{slice_a.name}` owners: `{slice_a.subprocess_nonzero_exit_owner_distribution}`",
        f"- `{slice_a.name}` actions: `{slice_a.subprocess_nonzero_exit_action_distribution}`",
        f"- `{slice_b.name}` count: `{slice_b.subprocess_nonzero_exit_count}`",
        f"- `{slice_b.name}` stages: `{slice_b.subprocess_nonzero_exit_stage_distribution}`",
        f"- `{slice_b.name}` owners: `{slice_b.subprocess_nonzero_exit_owner_distribution}`",
        f"- `{slice_b.name}` actions: `{slice_b.subprocess_nonzero_exit_action_distribution}`",
    ]
    return "\n".join(lines) + "\n"


def _extract_subprocess_stage(row: dict[str, Any]) -> str:
    summary_path = Path(str(row.get("_path", "")).strip())
    if not summary_path.exists():
        return "unknown"
    phase_dir = summary_path.parent
    evidence_files = sorted(
        [path for path in phase_dir.glob("evidence_phase_*.json") if path.is_file()],
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    if not evidence_files:
        return "unknown"
    try:
        payload = json.loads(evidence_files[0].read_text(encoding="utf-8"))
    except Exception:
        return "unknown"
    for event in payload.get("failure_events", []) or []:
        if str(event.get("cause_type", "")).strip().upper() != "AGENT_SUBPROCESS_NONZERO_EXIT":
            continue
        return str(event.get("stage", "")).strip() or "unknown"
    return "unknown"


def _owner_action_for_stage(stage: str) -> tuple[str, str]:
    text = str(stage).strip().lower()
    if text.startswith("planner"):
        return "planner", "retry_same_plan"
    if text.startswith("reviewer"):
        return "reviewer", "retry_same_plan"
    if text.startswith("qa"):
        return "qa", "replan_from_spec"
    if text.startswith("dev"):
        return "dev", "replan_from_spec"
    return "integrator", "replan_from_spec"
