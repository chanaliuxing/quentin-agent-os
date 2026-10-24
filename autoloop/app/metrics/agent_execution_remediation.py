from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from app.config import settings

TARGET_FAILURE_TYPE = "AGENT_SUBPROCESS_NONZERO_EXIT"


def analyze_subprocess_nonzero_exit(
    *,
    runtime_dir: Path | None = None,
    window_size: int = 20,
    min_count: int = 2,
    min_ratio: float = 0.2,
    real_only: bool = True,
) -> dict[str, Any]:
    root = runtime_dir or settings.runtime_dir
    rows = _collect_execution_summaries(root / "evidence")
    if real_only:
        rows = [row for row in rows if _is_real_run(str(row.get("workflow_id", "")))]
    rows = sorted(rows, key=lambda item: float(item.get("_mtime", 0.0)), reverse=True)
    window = rows[: max(1, int(window_size))]

    target = TARGET_FAILURE_TYPE
    matched = [row for row in window if str(row.get("primary_failure_type", "")).strip().upper() == target]
    stage_distribution: dict[str, int] = {}
    detail_rows: list[dict[str, Any]] = []
    for row in matched:
        detail = _load_subprocess_detail(row)
        stage = str(detail.get("stage", "")).strip() or "unknown"
        stage_distribution[stage] = stage_distribution.get(stage, 0) + 1
        detail_rows.append(
            {
                "workflow_id": str(row.get("workflow_id", "")),
                "phase_id": str(row.get("phase_id", "")),
                "summary_file": str(row.get("_path", "")),
                "stage": stage,
                "exit_code": detail.get("exit_code"),
                "execution_mode": str(detail.get("execution_mode", "")),
                "session_source": str(detail.get("session_source", "")),
                "error_message": str(detail.get("error_message", "")),
            }
        )

    top_stage = ""
    if stage_distribution:
        top_stage = sorted(stage_distribution.items(), key=lambda kv: (-int(kv[1]), kv[0]))[0][0]

    count = len(matched)
    total = len(window)
    ratio = (count / total) if total else 0.0
    triggered = bool(total and top_stage and (count >= int(min_count) or ratio > float(min_ratio)))
    latest = detail_rows[0] if detail_rows else {}

    return {
        "generated_at": datetime.now().isoformat(),
        "window_size": int(window_size),
        "evaluated_runs": int(total),
        "target_failure_type": target,
        "matched_count": int(count),
        "matched_ratio": round(float(ratio), 4),
        "triggered": bool(triggered),
        "top_stage": top_stage,
        "stage_distribution": dict(sorted(stage_distribution.items(), key=lambda kv: (-int(kv[1]), kv[0]))),
        "thresholds": {
            "min_count": int(min_count),
            "min_ratio": float(min_ratio),
            "real_only": bool(real_only),
        },
        "latest_match": latest,
    }


def create_execution_remediation_ticket_if_needed(
    *,
    analysis: dict[str, Any],
    runtime_dir: Path | None = None,
    dedupe_hours: int = 24,
) -> Path | None:
    if not bool(analysis.get("triggered")):
        return None

    root = runtime_dir or settings.runtime_dir
    hooks_dir = root / "hooks"
    hooks_dir.mkdir(parents=True, exist_ok=True)
    latest = dict(analysis.get("latest_match", {}) or {})
    target_failure_type = str(analysis.get("target_failure_type", TARGET_FAILURE_TYPE)).strip().upper()
    top_stage = str(analysis.get("top_stage", "")).strip() or "unknown"
    normalized_signature = f"{target_failure_type.lower()}:{top_stage.lower()}"

    if _recent_duplicate_exists(
        hooks_dir=hooks_dir,
        target_failure_type=target_failure_type,
        normalized_signature=normalized_signature,
        dedupe_hours=dedupe_hours,
    ):
        return None

    owner = _owner_for_stage(top_stage)
    recommended_action = _recommended_action_for_stage(top_stage)
    ticket = {
        "type": "execution_remediation_required",
        "created_at": datetime.now().isoformat(),
        "target_failure_type": target_failure_type,
        "top_stage": top_stage,
        "normalized_signature": normalized_signature,
        "window_size": int(analysis.get("window_size", 0)),
        "matched_count": int(analysis.get("matched_count", 0)),
        "matched_ratio": float(analysis.get("matched_ratio", 0.0)),
        "recommended_action": recommended_action,
        "owner": owner,
        "workflow_id": str(latest.get("workflow_id", "")),
        "phase_id": str(latest.get("phase_id", "")),
        "summary_file": str(latest.get("summary_file", "")),
        "stage": str(latest.get("stage", "")),
        "exit_code": latest.get("exit_code"),
        "execution_mode": str(latest.get("execution_mode", "")),
        "session_source": str(latest.get("session_source", "")),
        "error_message": str(latest.get("error_message", "")),
        "stage_distribution": dict(analysis.get("stage_distribution", {}) or {}),
    }
    filename = f"execution_ticket_{datetime.now().strftime('%Y%m%d%H%M%S')}.json"
    target = hooks_dir / filename
    target.write_text(json.dumps(ticket, ensure_ascii=False, indent=2), encoding="utf-8")
    return target


def write_execution_remediation_report(
    *,
    analysis: dict[str, Any],
    runtime_dir: Path | None = None,
) -> Path:
    root = runtime_dir or settings.runtime_dir
    path = root / "metrics" / "agent_execution_remediation_report.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(analysis, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


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
        if str(event.get("cause_type", "")).strip().upper() != TARGET_FAILURE_TYPE:
            continue
        detail = dict(event.get("payload", {}) or {}).get("subprocess_detail", {}) or {}
        if not isinstance(detail, dict):
            detail = {}
        merged = dict(detail)
        merged["stage"] = str(event.get("stage", "")).strip()
        return merged
    return {}


def _owner_for_stage(stage: str) -> str:
    text = str(stage).strip().lower()
    if text.startswith("planner"):
        return "planner"
    if text.startswith("reviewer"):
        return "reviewer"
    if text.startswith("qa"):
        return "qa"
    return "dev"


def _recommended_action_for_stage(stage: str) -> str:
    text = str(stage).strip().lower()
    if text.startswith("planner") or text.startswith("reviewer"):
        return "retry_same_plan"
    return "replan_from_spec"


def _recent_duplicate_exists(
    *,
    hooks_dir: Path,
    target_failure_type: str,
    normalized_signature: str,
    dedupe_hours: int,
) -> bool:
    threshold = datetime.now() - timedelta(hours=max(1, int(dedupe_hours)))
    for path in hooks_dir.glob("execution_ticket_*.json"):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if str(payload.get("target_failure_type", "")).strip().upper() != target_failure_type.strip().upper():
            continue
        if str(payload.get("normalized_signature", "")).strip() != normalized_signature:
            continue
        created_at = str(payload.get("created_at", "")).strip()
        try:
            created_dt = datetime.fromisoformat(created_at)
        except Exception:
            continue
        if created_dt >= threshold:
            return True
    return False


def _is_real_run(run_id: str) -> bool:
    normalized = str(run_id).strip().lower()
    if not normalized:
        return False
    return normalized.startswith(("real-", "prod-", "sweep-", "codex-canary-"))
