#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.config import settings
from app.control import expected_terminal_state_for_recovery
from app.control import evaluate_recovery_rollout, load_recovery_rollout_policy


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--window-size", type=int, default=50)
    parser.add_argument("--real-only", action="store_true", default=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    policy = load_recovery_rollout_policy()
    rows = _collect_summaries(settings.runtime_dir / "evidence")
    if args.real_only:
        rows = [row for row in rows if _is_real_run(str(row.get("workflow_id", "")))]
    rows = sorted(rows, key=lambda item: float(item.get("_mtime", 0.0)), reverse=True)[: max(1, args.window_size)]
    decisions = []
    terminal_match = 0
    for row in rows:
        action = str(row.get("recovery_action", "")).strip()
        failure_type = str(row.get("primary_failure_type", "")).strip().upper()
        phase = str(row.get("phase_id", "")).strip() or "phase_01"
        run_id = str(row.get("workflow_id", "")).strip()
        result = evaluate_recovery_rollout(
            policy=policy,
            project_id=run_id,
            phase_id=phase,
            action=action,
            primary_failure_type=failure_type,
            acceptance_status=str(row.get("acceptance_status", "")),
            retry_count=int(row.get("replan_rounds", 0)),
        )
        expected_terminal = expected_terminal_state_for_recovery(
            failure_type=failure_type,
            recovery_action=action,
        )
        actual_terminal = str(row.get("terminal_state", "")).strip().upper()
        match = bool(expected_terminal and actual_terminal == expected_terminal)
        if match:
            terminal_match += 1
        decisions.append(
            {
                "workflow_id": run_id,
                "phase_id": phase,
                "failure_type": failure_type,
                "recovery_action": action,
                "decision": result,
                "expected_terminal_state": expected_terminal,
                "actual_terminal_state": actual_terminal,
                "terminal_match": match,
            }
        )
    action_counter = Counter(str(item.get("recovery_action", "")).strip() for item in decisions if str(item.get("recovery_action", "")).strip())
    execution_counter = Counter(str(item.get("decision", {}).get("reason", "")).strip() for item in decisions)
    top2_types = {"AGENT_OUTPUT_MISSING", "AGENT_RESULT_PARSE_FAILED"}
    top2_rows = [item for item in decisions if str(item.get("failure_type", "")).strip().upper() in top2_types]
    top2_match = sum(
        1
        for item in top2_rows
        if str(item.get("expected_terminal_state", "")).strip().upper()
        and str(item.get("actual_terminal_state", "")).strip().upper()
        == str(item.get("expected_terminal_state", "")).strip().upper()
    )
    report = {
        "generated_at": datetime.now().isoformat(),
        "window_size": int(args.window_size),
        "evaluated_runs": len(rows),
        "policy_mode": str(policy.get("mode", "")),
        "action_distribution": dict(action_counter),
        "decision_distribution": dict(execution_counter),
        "terminal_state_expected_match_rate": round(terminal_match / len(rows), 4) if rows else 1.0,
        "top2_execution_subtype_terminal_match": {
            "tracked_types": sorted(top2_types),
            "evaluated": len(top2_rows),
            "matched": top2_match,
            "match_rate": round(top2_match / len(top2_rows), 4) if top2_rows else 1.0,
        },
        "samples": decisions[:20],
    }
    out = settings.runtime_dir / "metrics" / "recovery_canary_report.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(out)
    return 0


def _collect_summaries(evidence_root: Path) -> list[dict]:
    rows = []
    if not evidence_root.exists():
        return rows
    for path in evidence_root.rglob("execution_summary.json"):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        payload["_mtime"] = path.stat().st_mtime
        rows.append(payload)
    return rows


def _is_real_run(run_id: str) -> bool:
    normalized = str(run_id).strip().lower()
    return normalized.startswith(("real-", "prod-", "sweep-", "codex-canary-"))


if __name__ == "__main__":
    raise SystemExit(main())
