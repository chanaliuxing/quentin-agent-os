from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from app.config import settings
from app.evidence import EventRecord, EventStore, ExecutionSummary, ExecutionSummaryStore


def _normalize_primary(primary_failure_type: str, terminal_state: str) -> str:
    code = str(primary_failure_type).strip().upper()
    state = str(terminal_state).strip().upper()
    if state == "ACCEPTED":
        return ""
    if code and code not in {"NONE", "UNKNOWN", "UNKNOWN_FAILURE", "NULL"}:
        return code
    if state == "REJECTED":
        return "UNCLASSIFIED_BUSINESS_FAILURE"
    if state in {"ABORTED", "TIMEOUT"}:
        return "UNCLASSIFIED_EXECUTION_FAILURE"
    return "UNCLASSIFIED_ENVIRONMENT_FAILURE"


def write_terminal_event_once(
    *,
    project_id: str,
    phase_id: str,
    terminal_state: str,
    final_status_label: str,
    recommended_action: str,
    acceptance_status: str,
    primary_failure_type: str,
    secondary_failure_types: list[str],
    failure_events: list[dict],
    termination_reason: str,
    trace_id: str,
) -> dict:
    now = datetime.now().isoformat()
    control_dir = settings.runtime_dir / "control"
    control_dir.mkdir(parents=True, exist_ok=True)
    once_file = control_dir / f"terminal_once_{project_id}_{phase_id}.json"
    if once_file.exists():
        try:
            return json.loads(once_file.read_text(encoding="utf-8"))
        except Exception:
            pass

    event_store = EventStore()
    terminal_event_id = f"{project_id}.{phase_id}.workflow.{datetime.now().strftime('%Y%m%d%H%M%S%f')}"
    primary = _normalize_primary(primary_failure_type, terminal_state)
    secondary = [str(item) for item in secondary_failure_types if str(item).strip()]
    if str(terminal_state).strip().upper() == "ACCEPTED":
        secondary = []
    first_failure_event_id = ""
    first_failure_at = ""
    if failure_events:
        first = failure_events[0]
        first_failure_event_id = str(first.get("event_id", "")).strip()
        first_failure_at = str(first.get("event_time", "")).strip()
    if not first_failure_at:
        first_failure_at = now

    event_store.append(
        EventRecord(
            event_id=terminal_event_id,
            event_time=now,
            workflow_id=project_id,
            run_id=project_id,
            phase_id=phase_id,
            stage="workflow",
            actor="workflow",
            event_type="WORKFLOW_TERMINATED",
            cause_class="terminal",
            failure_type=primary,
            payload={
                "terminal_state": terminal_state,
                "final_status_label": final_status_label,
                "recommended_action": recommended_action,
                "termination_reason": termination_reason,
                "failure_events": failure_events[-20:],
            },
            trace_id=trace_id,
        )
    )

    summary_path = ExecutionSummaryStore().write(
        ExecutionSummary(
            workflow_id=project_id,
            phase_id=phase_id,
            primary_failure_type=primary,
            secondary_failure_types=secondary,
            first_failure_at=first_failure_at,
            first_failure_event_id=first_failure_event_id,
            final_status_label=final_status_label,
            terminal_state=terminal_state,
            finalized_at=now,
            terminal_event_id=terminal_event_id,
            recovery_action=recommended_action,
            acceptance_status=acceptance_status,
        )
    )
    output = {
        "terminal_event_id": terminal_event_id,
        "execution_summary_file": str(summary_path),
        "primary_failure_type": primary,
        "finalized_at": now,
        "termination_reason": termination_reason,
    }
    once_file.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    return output
