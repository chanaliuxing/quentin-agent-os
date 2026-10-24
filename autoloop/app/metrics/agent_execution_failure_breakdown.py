from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from app.config import settings
from app.control import load_failure_router_policy

AGENT_EXECUTION_SUBTYPES = {
    "AGENT_SUBPROCESS_NONZERO_EXIT",
    "AGENT_OUTPUT_MISSING",
    "AGENT_CONTRACT_VIOLATION",
    "AGENT_ARTIFACT_WRITE_FAILED",
    "AGENT_RUNNER_SESSION_DEGRADED",
    "AGENT_RESULT_PARSE_FAILED",
}
TOP2_EXECUTION_SUBTYPES = {
    "AGENT_OUTPUT_MISSING",
    "AGENT_RESULT_PARSE_FAILED",
}


def build_agent_execution_failure_breakdown(
    *,
    runtime_dir: Path | None = None,
    window_size: int = 20,
    real_only: bool = True,
) -> dict[str, Any]:
    root = runtime_dir or settings.runtime_dir
    rows = _collect_execution_summaries(root / "evidence")
    if real_only:
        rows = [row for row in rows if _is_real_run(str(row.get("workflow_id", "")))]
    rows = sorted(rows, key=lambda item: float(item.get("_mtime", 0.0)), reverse=True)
    window_size = max(1, int(window_size))
    current_window = rows[:window_size]
    previous_window = rows[window_size : window_size * 2]
    policy = load_failure_router_policy()

    current = _summarize_window(current_window, policy=policy)
    previous = _summarize_window(previous_window, policy=policy)
    nonzero_breakdown = _summarize_subprocess_nonzero_exit(current_window)
    distribution = current["distribution"]
    total = int(current["total"])
    parent_count = int(current["parent_count"])
    unmapped = [code for code in distribution.keys() if code not in AGENT_EXECUTION_SUBTYPES and code != "AGENT_EXECUTION_FAILED"]
    trend: dict[str, dict[str, int]] = {}
    tracked_codes = sorted(set(distribution.keys()) | set(previous["distribution"].keys()))
    for code in tracked_codes:
        trend[code] = {
            "current": int(distribution.get(code, 0)),
            "previous": int(previous["distribution"].get(code, 0)),
            "delta": int(distribution.get(code, 0) - previous["distribution"].get(code, 0)),
        }
    return {
        "generated_at": datetime.now().isoformat(),
        "window_size": int(window_size),
        "evaluated_runs": len(current_window),
        "agent_execution_failures_in_window": total,
        "distribution": distribution,
        "agent_execution_failed_parent_count": parent_count,
        "agent_execution_failed_parent_ratio": round((parent_count / total), 4) if total else 0.0,
        "agent_execution_failed_parent_ratio_all_runs": round((parent_count / len(current_window)), 4) if current_window else 0.0,
        "previous_window_size": len(previous_window),
        "trend_vs_previous_window": trend,
        "top2_subtype_recovery_match": current["top2_recovery"],
        "subprocess_nonzero_exit_breakdown": nonzero_breakdown,
        "unmapped_agent_failure_types": sorted(unmapped),
    }


def write_agent_execution_failure_breakdown_report(
    *,
    runtime_dir: Path | None = None,
    window_size: int = 20,
    real_only: bool = True,
) -> Path:
    root = runtime_dir or settings.runtime_dir
    report = build_agent_execution_failure_breakdown(
        runtime_dir=root,
        window_size=window_size,
        real_only=real_only,
    )
    target = root / "metrics" / "agent_execution_failure_breakdown_report.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return target


def _collect_execution_summaries(evidence_root: Path) -> list[dict[str, Any]]:
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


def _is_real_run(run_id: str) -> bool:
    normalized = str(run_id).strip().lower()
    if not normalized:
        return False
    return normalized.startswith(("real-", "prod-", "sweep-", "codex-canary-"))


def _summarize_window(rows: list[dict[str, Any]], *, policy: dict[str, Any]) -> dict[str, Any]:
    failure_type_actions = dict(policy.get("failure_type_actions", {}) or {})
    distribution: dict[str, int] = {}
    parent_count = 0
    total = 0
    top2_total = 0
    top2_match = 0
    for item in rows:
        failure_type = str(item.get("primary_failure_type", "")).strip().upper()
        if not failure_type.startswith("AGENT_"):
            continue
        total += 1
        distribution[failure_type] = distribution.get(failure_type, 0) + 1
        if failure_type == "AGENT_EXECUTION_FAILED":
            parent_count += 1
        if failure_type in TOP2_EXECUTION_SUBTYPES:
            top2_total += 1
            expected = str(dict(failure_type_actions.get(failure_type, {}) or {}).get("action", "")).strip()
            actual = str(item.get("recovery_action", "")).strip()
            if expected and actual and expected == actual:
                top2_match += 1
    return {
        "distribution": distribution,
        "parent_count": parent_count,
        "total": total,
        "top2_recovery": {
            "evaluated": top2_total,
            "matched": top2_match,
            "match_rate": round((top2_match / top2_total), 4) if top2_total else 1.0,
            "tracked_types": sorted(TOP2_EXECUTION_SUBTYPES),
        },
    }


def _summarize_subprocess_nonzero_exit(rows: list[dict[str, Any]]) -> dict[str, Any]:
    by_exit_code: dict[str, int] = {}
    by_stage: dict[str, int] = {}
    examples: list[dict[str, Any]] = []
    for item in rows:
        if str(item.get("primary_failure_type", "")).strip().upper() != "AGENT_SUBPROCESS_NONZERO_EXIT":
            continue
        detail = _load_subprocess_detail(item)
        exit_code = str(detail.get("exit_code", "")).strip() or "<unknown>"
        stage = str(detail.get("stage", "")).strip() or "<unknown>"
        by_exit_code[exit_code] = by_exit_code.get(exit_code, 0) + 1
        by_stage[stage] = by_stage.get(stage, 0) + 1
        if len(examples) < 5:
            examples.append(
                {
                    "workflow_id": str(item.get("workflow_id", "")),
                    "phase_id": str(item.get("phase_id", "")),
                    "stage": stage,
                    "exit_code": exit_code,
                    "execution_mode": str(detail.get("execution_mode", "")).strip(),
                    "session_source": str(detail.get("session_source", "")).strip(),
                    "error_message": str(detail.get("error_message", "")).strip(),
                }
            )
    return {
        "count": sum(by_exit_code.values()),
        "by_exit_code": dict(sorted(by_exit_code.items(), key=lambda x: (-x[1], x[0]))),
        "by_stage": dict(sorted(by_stage.items(), key=lambda x: (-x[1], x[0]))),
        "examples": examples,
    }


def _load_subprocess_detail(summary_row: dict[str, Any]) -> dict[str, Any]:
    summary_path = Path(str(summary_row.get("_path", "")).strip())
    if not summary_path.exists():
        return {}
    phase_dir = summary_path.parent
    evidence_files = sorted(
        [path for path in phase_dir.glob("evidence_phase_*.json") if path.is_file()],
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    if not evidence_files:
        return {}
    try:
        payload = json.loads(evidence_files[0].read_text(encoding="utf-8"))
    except Exception:
        return {}
    for event in payload.get("failure_events", []) or []:
        if str(event.get("cause_type", "")).strip().upper() != "AGENT_SUBPROCESS_NONZERO_EXIT":
            continue
        detail = dict(event.get("payload", {}) or {}).get("subprocess_detail", {}) or {}
        if not isinstance(detail, dict):
            detail = {}
        merged = dict(detail)
        merged["stage"] = str(event.get("stage", "")).strip()
        return merged
    return {}
