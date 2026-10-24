#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.temporal.workflow import _derive_failure_diagnostics, _derive_terminal_state


@dataclass
class Scenario:
    name: str
    acceptance_status: str
    recommended_action: str
    events: list[dict]
    expected_primary: str
    expected_terminal: str


SCENARIOS = [
    Scenario(
        name="path_conflict",
        acceptance_status="rejected",
        recommended_action="replan_from_spec",
        events=[
            {
                "event_id": "wf.phase.reviewer.001",
                "event_time": "2026-03-08T00:00:00Z",
                "failure_type": "PATH_CONFLICT",
                "stage": "reviewer",
                "actor": "activity",
                "cause_class": "business",
            }
        ],
        expected_primary="PATH_CONFLICT",
        expected_terminal="REJECTED",
    ),
    Scenario(
        name="missing_required_test",
        acceptance_status="rejected",
        recommended_action="replan_from_spec",
        events=[
            {
                "event_id": "wf.phase.qa.001",
                "event_time": "2026-03-08T00:00:00Z",
                "failure_type": "MISSING_REQUIRED_TEST",
                "stage": "required_test_missing",
                "actor": "activity",
                "cause_class": "contract",
            }
        ],
        expected_primary="MISSING_REQUIRED_TEST",
        expected_terminal="REJECTED",
    ),
    Scenario(
        name="grader_failed",
        acceptance_status="rejected",
        recommended_action="replan_from_spec",
        events=[
            {
                "event_id": "wf.phase.qa.002",
                "event_time": "2026-03-08T00:00:01Z",
                "failure_type": "GRADER_FAILED",
                "stage": "grader_failed",
                "actor": "activity",
                "cause_class": "business",
            }
        ],
        expected_primary="GRADER_FAILED",
        expected_terminal="REJECTED",
    ),
    Scenario(
        name="business_unmapped",
        acceptance_status="rejected",
        recommended_action="taxonomy_review_required",
        events=[
            {
                "event_id": "wf.phase.workflow.003",
                "event_time": "2026-03-08T00:00:02Z",
                "failure_type": "BUSINESS_REJECTION_UNMAPPED",
                "stage": "unclassified_failure",
                "actor": "workflow",
                "cause_class": "business",
            }
        ],
        expected_primary="BUSINESS_REJECTION_UNMAPPED",
        expected_terminal="REJECTED",
    ),
    Scenario(
        name="state_db_degraded",
        acceptance_status="rejected",
        recommended_action="escalate_to_human",
        events=[
            {
                "event_id": "wf.phase.runner.001",
                "event_time": "2026-03-08T00:00:00Z",
                "failure_type": "STATE_DB_DEGRADED",
                "stage": "dev",
                "actor": "activity",
                "cause_class": "environment",
            }
        ],
        expected_primary="STATE_DB_DEGRADED",
        expected_terminal="ABORTED",
    ),
    Scenario(
        name="global_timeout",
        acceptance_status="rejected",
        recommended_action="replan_from_spec",
        events=[
            {
                "event_id": "wf.phase.dev.001",
                "event_time": "2026-03-08T00:00:00Z",
                "failure_type": "GLOBAL_TIMEOUT",
                "stage": "dev",
                "actor": "activity",
                "cause_class": "execution",
            }
        ],
        expected_primary="GLOBAL_TIMEOUT",
        expected_terminal="TIMEOUT",
    ),
]


def _check_event_completeness(events: list[dict]) -> dict:
    required_fields = ("event_time", "stage", "actor", "cause_type", "cause_class")
    missing = 0
    for event in events:
        if any(not str(event.get(key, "")).strip() for key in required_fields):
            missing += 1
    total = len(events)
    complete = max(0, total - missing)
    rate = 1.0 if total == 0 else complete / total
    return {"total_events": total, "complete_events": complete, "completeness_rate": round(rate, 4)}


def main() -> int:
    scenario_results: list[dict] = []
    consistency_passed = 0
    total = len(SCENARIOS)
    for scenario in SCENARIOS:
        diagnostics = _derive_failure_diagnostics(
            results={},
            test_results={"status": "failed", "acceptance_status": scenario.acceptance_status},
            failed_modules=[],
            events=scenario.events,
        )
        terminal_state = _derive_terminal_state(
            acceptance_status=scenario.acceptance_status,
            recommended_action=scenario.recommended_action,
            failure_diagnostics=diagnostics,
        )
        pass_primary = diagnostics.get("primary_failure_type") == scenario.expected_primary
        pass_terminal = terminal_state == scenario.expected_terminal
        if pass_primary and pass_terminal:
            consistency_passed += 1
        completeness = _check_event_completeness(diagnostics.get("failure_events", []))
        scenario_results.append(
            {
                "scenario": scenario.name,
                "expected_primary": scenario.expected_primary,
                "actual_primary": diagnostics.get("primary_failure_type", ""),
                "expected_terminal": scenario.expected_terminal,
                "actual_terminal": terminal_state,
                "pass_primary": pass_primary,
                "pass_terminal": pass_terminal,
                "first_failure_event_id": diagnostics.get("first_failure_event_id", ""),
                "event_completeness": completeness,
            }
        )

    report = {
        "generated_at": datetime.now().isoformat(),
        "terminal_state_consistency": {
            "passed": consistency_passed,
            "total": total,
            "pass_rate": round(consistency_passed / total, 4) if total else 1.0,
        },
        "scenarios": scenario_results,
    }
    output_path = Path("runtime/metrics/control_plane_matrix_report.json")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(output_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
