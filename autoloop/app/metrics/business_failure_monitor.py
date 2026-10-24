from __future__ import annotations

import json
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from app.config import settings

TARGET_FAILURE_TYPE = "BUSINESS_REJECTION_UNMAPPED"


def analyze_rolling_business_failure(
    *,
    runtime_dir: Path | None = None,
    window_size: int = 20,
    target_failure_type: str = TARGET_FAILURE_TYPE,
    min_count: int = 2,
    min_ratio: float = 0.05,
    real_only: bool = True,
) -> dict[str, Any]:
    root = runtime_dir or settings.runtime_dir
    rows = _collect_execution_summaries(root / "evidence")
    if real_only:
        rows = [row for row in rows if _is_real_run(str(row.get("workflow_id", "")))]
    rows = sorted(rows, key=lambda item: float(item.get("_mtime", 0.0)), reverse=True)
    window = rows[: max(1, window_size)]
    target = str(target_failure_type).strip().upper()
    matched = [
        row
        for row in window
        if str(row.get("primary_failure_type", "")).strip().upper() == target
    ]
    count = len(matched)
    total = len(window)
    ratio = float(count / total) if total else 0.0
    latest = matched[0] if matched else {}
    triggered = bool(total and (count >= int(min_count) or ratio > float(min_ratio)))
    return {
        "generated_at": datetime.now().isoformat(),
        "window_size": int(window_size),
        "evaluated_runs": total,
        "target_failure_type": target,
        "matched_count": count,
        "matched_ratio": round(ratio, 4),
        "triggered": triggered,
        "thresholds": {
            "min_count": int(min_count),
            "min_ratio": float(min_ratio),
            "real_only": bool(real_only),
        },
        "latest_match": {
            "workflow_id": str(latest.get("workflow_id", "")),
            "phase_id": str(latest.get("phase_id", "")),
            "primary_failure_type": str(latest.get("primary_failure_type", "")),
            "terminal_state": str(latest.get("terminal_state", "")),
            "recovery_action": str(latest.get("recovery_action", "")),
            "failure_signature": str(latest.get("failure_signature", "")),
            "first_failure_stage": str(latest.get("first_failure_stage", "")),
            "summary_file": str(latest.get("_path", "")),
            "failure_events": latest.get("failure_events", []),
        },
    }


def create_taxonomy_ticket_if_needed(
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
    normalized_signature = _normalized_signature(latest)
    if _recent_duplicate_exists(
        hooks_dir=hooks_dir,
        target_failure_type=str(analysis.get("target_failure_type", "")),
        normalized_signature=normalized_signature,
        dedupe_hours=dedupe_hours,
    ):
        return None
    ticket = {
        "type": "taxonomy_review_required",
        "created_at": datetime.now().isoformat(),
        "target_failure_type": str(analysis.get("target_failure_type", "")),
        "normalized_signature": normalized_signature,
        "window_size": int(analysis.get("window_size", 0)),
        "matched_count": int(analysis.get("matched_count", 0)),
        "matched_ratio": float(analysis.get("matched_ratio", 0.0)),
        "workflow_id": str(latest.get("workflow_id", "")),
        "phase_id": str(latest.get("phase_id", "")),
        "primary_failure_type": str(latest.get("primary_failure_type", "")),
        "terminal_state": str(latest.get("terminal_state", "")),
        "recovery_action": str(latest.get("recovery_action", "")) or "taxonomy_review_required",
        "evidence_summary_file": str(latest.get("summary_file", "")),
        "failure_events": list(latest.get("failure_events", []) or []),
    }
    filename = f"taxonomy_ticket_{datetime.now().strftime('%Y%m%d%H%M%S')}.json"
    target = hooks_dir / filename
    target.write_text(json.dumps(ticket, ensure_ascii=False, indent=2), encoding="utf-8")
    return target


def write_business_failure_monitor_report(
    *,
    analysis: dict[str, Any],
    runtime_dir: Path | None = None,
) -> Path:
    root = runtime_dir or settings.runtime_dir
    payload = dict(analysis)
    remediation_path = root / "metrics" / "agent_execution_remediation_report.json"
    if remediation_path.exists():
        try:
            payload["execution_remediation_snapshot"] = json.loads(
                remediation_path.read_text(encoding="utf-8")
            )
        except Exception:
            payload["execution_remediation_snapshot"] = {}
    path = root / "metrics" / "business_failure_monitor_report.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
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


def _normalized_signature(latest: dict[str, Any]) -> str:
    signature = str(latest.get("failure_signature", "")).strip().lower()
    if not signature:
        signature = str(latest.get("first_failure_stage", "")).strip().lower()
    if not signature:
        events = latest.get("failure_events", [])
        if isinstance(events, list):
            types = sorted(
                {
                    str(item.get("cause_type", "")).strip().lower()
                    for item in events
                    if isinstance(item, dict) and str(item.get("cause_type", "")).strip()
                }
            )
            signature = "|".join(types)
    if not signature:
        signature = "unknown_signature"
    return re.sub(r"[^a-z0-9_|:-]+", "_", signature)


def _recent_duplicate_exists(
    *,
    hooks_dir: Path,
    target_failure_type: str,
    normalized_signature: str,
    dedupe_hours: int,
) -> bool:
    threshold = datetime.now() - timedelta(hours=max(1, int(dedupe_hours)))
    for path in hooks_dir.glob("taxonomy_ticket_*.json"):
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
    return normalized.startswith(("real-", "prod-"))
