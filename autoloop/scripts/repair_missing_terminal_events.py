#!/usr/bin/env python3
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path


def _read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except Exception:
            continue
    return rows


def _append_jsonl(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as file:
        file.write(json.dumps(payload, ensure_ascii=False))
        file.write("\n")


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    evidence_root = root / "runtime" / "evidence"
    event_root = root / "runtime" / "event_log"
    repaired = 0

    for summary_file in evidence_root.rglob("execution_summary.json"):
        summary = _read_json(summary_file)
        workflow_id = str(summary.get("workflow_id", "")).strip()
        phase_id = str(summary.get("phase_id", "")).strip()
        if not workflow_id or not phase_id:
            continue
        event_file = event_root / workflow_id / phase_id / "events.jsonl"
        events = _read_jsonl(event_file)
        if any(str(item.get("event_type", "")).strip() == "WORKFLOW_TERMINATED" for item in events):
            continue
        now = datetime.now().isoformat()
        payload = {
            "event_id": f"{workflow_id}.{phase_id}.workflow.repair.{datetime.now().strftime('%Y%m%d%H%M%S%f')}",
            "event_time": now,
            "workflow_id": workflow_id,
            "run_id": workflow_id,
            "phase_id": phase_id,
            "stage": "workflow",
            "actor": "system",
            "event_type": "WORKFLOW_TERMINATED",
            "attempt": 1,
            "cause_class": "terminal",
            "failure_type": str(summary.get("primary_failure_type", "")),
            "payload": {
                "terminal_state": str(summary.get("terminal_state", "")),
                "final_status_label": str(summary.get("final_status_label", "")),
                "recommended_action": str(summary.get("recovery_action", "")),
                "termination_reason": "repair_missing_terminal_event",
            },
            "artifact_refs": [str(summary_file)],
            "trace_id": f"{workflow_id}:{phase_id}",
            "parent_event_id": None,
            "supersedes_event_id": None,
            "created_at": now,
        }
        _append_jsonl(event_file, payload)
        repaired += 1

    print(json.dumps({"repaired_runs": repaired}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
