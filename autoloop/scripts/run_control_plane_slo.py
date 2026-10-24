#!/usr/bin/env python3
from __future__ import annotations

import json
import os
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

PRIMARY_PRIORITY = [
    "PATH_CONFLICT",
    "MISSING_TEST_BINDING",
    "INVALID_CHANGE_CONTRACT",
    "INVALID_ACCEPTANCE_CONTRACT",
    "MISSING_REQUIRED_TEST",
    "GRADER_FAILED",
    "BUSINESS_TEST_POLICY_GAP",
    "BUSINESS_GRADER_CONTRACT_GAP",
    "BUSINESS_REJECTION_UNMAPPED",
    "BUSINESS_EVIDENCE_MISSING",
    "MISSING_DEV_RESULT",
    "MISSING_QA_RESULT",
    "RUNNER_BLOCKED",
    "STATE_DB_DEGRADED",
    "GLOBAL_TIMEOUT",
]


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


def _collect_execution_summaries(evidence_root: Path) -> list[dict]:
    summaries: list[dict] = []
    for path in evidence_root.rglob("execution_summary.json"):
        payload = _read_json(path)
        if payload:
            payload["_path"] = str(path)
            payload["_mtime"] = path.stat().st_mtime
            summaries.append(payload)
    summaries.sort(key=lambda item: float(item.get("_mtime", 0.0)), reverse=True)
    return summaries


def _collect_evidence_records(evidence_root: Path) -> list[dict]:
    rows: list[dict] = []
    for path in evidence_root.rglob("evidence_phase_*.json"):
        payload = _read_json(path)
        if payload:
            payload["_path"] = str(path)
            payload["_mtime"] = path.stat().st_mtime
            rows.append(payload)
    rows.sort(key=lambda item: float(item.get("_mtime", 0.0)), reverse=True)
    return rows


def _collect_event_logs(event_root: Path) -> dict[str, list[dict]]:
    logs: dict[str, list[dict]] = {}
    for path in event_root.rglob("events.jsonl"):
        events = _read_jsonl(path)
        key = "/".join(path.parts[-3:-1])
        logs[key] = events
    return logs


def _calc_unknown_failure_rate(summaries: list[dict]) -> float:
    if not summaries:
        return 0.0
    unknown = 0
    for item in summaries:
        code = str(item.get("primary_failure_type", "")).strip().upper()
        if code in {"", "UNKNOWN", "UNKNOWN_FAILURE", "NONE", "NULL"}:
            unknown += 1
    return round(unknown / len(summaries), 4)


def _calc_terminal_state_consistency(summaries: list[dict]) -> tuple[float, dict[str, list[str]]]:
    by_primary: dict[str, set[str]] = defaultdict(set)
    for item in summaries:
        primary = str(item.get("primary_failure_type", "")).strip().upper()
        terminal = str(item.get("terminal_state", "")).strip().upper()
        if not primary or not terminal:
            continue
        by_primary[primary].add(terminal)
    if not by_primary:
        return 1.0, {}
    stable = sum(1 for terminals in by_primary.values() if len(terminals) == 1)
    rate = round(stable / len(by_primary), 4)
    return rate, {key: sorted(value) for key, value in by_primary.items()}


def _calc_event_completeness(
    logs: dict[str, list[dict]],
    terminal_run_keys: set[str],
) -> tuple[float, dict[str, dict]]:
    required = {"WORKFLOW_STARTED", "WORKFLOW_TERMINATED"}
    details: dict[str, dict] = {}
    if not terminal_run_keys:
        return 0.0, details
    target_logs = {key: logs.get(key, []) for key in terminal_run_keys}
    complete_runs = 0
    for run_key, events in target_logs.items():
        event_types = {str(item.get("event_type", "")).strip() for item in events}
        is_complete = required.issubset(event_types)
        if is_complete:
            complete_runs += 1
        missing = sorted(required - event_types)
        details[run_key] = {
            "event_count": len(events),
            "missing_event_types": missing,
            "gate_failure_type": "MISSING_TERMINAL_EVENT" if "WORKFLOW_TERMINATED" in missing else "",
            "complete": is_complete,
        }
    return round(complete_runs / len(target_logs), 4), details


def _calc_primary_hit_rate(matrix_report: dict) -> float:
    scenarios = matrix_report.get("scenarios", [])
    if not scenarios:
        return 0.0
    passed = sum(1 for item in scenarios if bool(item.get("pass_primary")))
    return round(passed / len(scenarios), 4)


def _is_unknown(code: str) -> bool:
    return code in {"", "UNKNOWN", "UNKNOWN_FAILURE", "NONE", "NULL"}


def _priority(code: str) -> int:
    normalized = str(code).strip().upper()
    if normalized in PRIMARY_PRIORITY:
        return PRIMARY_PRIORITY.index(normalized)
    return 999


def _normalize_summary_primary(*, summary: dict, logs: dict[str, list[dict]]) -> str:
    primary = str(summary.get("primary_failure_type", "")).strip().upper()
    if not _is_unknown(primary):
        return primary
    key = f"{summary.get('workflow_id', '')}/{summary.get('phase_id', '')}"
    events = logs.get(key, [])
    event_codes = []
    for event in events:
        code = str(event.get("failure_type", "")).strip().upper()
        if _is_unknown(code):
            continue
        event_codes.append((code, str(event.get("event_time", ""))))
    if not event_codes:
        terminal = str(summary.get("terminal_state", "")).strip().upper()
        acceptance = str(summary.get("acceptance_status", "")).strip().lower()
        if terminal == "TIMEOUT":
            return "UNCLASSIFIED_EXECUTION_FAILURE"
        if terminal in {"FAILED", "ABORTED"}:
            return "UNCLASSIFIED_EXECUTION_FAILURE"
        if acceptance == "rejected":
            return "UNCLASSIFIED_BUSINESS_FAILURE"
        return "UNCLASSIFIED_ENVIRONMENT_FAILURE"
    event_codes.sort(key=lambda item: (_priority(item[0]), item[1]))
    return event_codes[0][0]


def _unknown_source_breakdown(summaries: list[dict]) -> dict[str, int]:
    breakdown: Counter[str] = Counter()
    for item in summaries:
        code = str(item.get("primary_failure_type", "")).strip().upper()
        if code in {"", "UNKNOWN", "UNKNOWN_FAILURE", "NONE", "NULL"}:
            terminal = str(item.get("terminal_state", "")).strip().upper() or "UNKNOWN_TERMINAL"
            breakdown[terminal] += 1
    return dict(breakdown)


def _has_required_test_detail_contract(*, test_name: str, details: list[str]) -> bool:
    normalized = [str(item).strip() for item in details if str(item).strip()]
    if not normalized:
        return False
    joined = "\n".join(normalized)
    required_tokens = [
        f"required_test={test_name}",
        "failure_type=",
        "location=",
    ]
    return all(token in joined for token in required_tokens)


def _calc_required_test_failure_detail_missing_rate(records: list[dict]) -> tuple[float, list[dict]]:
    required_test_failed_records = [
        item
        for item in records
        if str(item.get("primary_failure_type", "")).strip().upper() == "REQUIRED_TEST_FAILED"
    ]
    if not required_test_failed_records:
        return 0.0, []

    violations: list[dict] = []
    for item in required_test_failed_records:
        failed_tests = [str(x).strip() for x in item.get("failed_required_tests", []) if str(x).strip()]
        details_map = item.get("required_test_failure_details", {}) or {}
        missing_tests = [
            test_name
            for test_name in failed_tests
            if not _has_required_test_detail_contract(
                test_name=test_name,
                details=list(details_map.get(test_name, []) or []),
            )
        ]
        if missing_tests:
            violations.append(
                {
                    "run_id": str(item.get("run_id", "")),
                    "phase_id": str(item.get("phase_id", "")),
                    "missing_tests": sorted(set(missing_tests)),
                    "gate_failure_type": "MISSING_REQUIRED_TEST_FAILURE_DETAIL",
                }
            )
    rate = round(len(violations) / len(required_test_failed_records), 4)
    return rate, violations


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    gate_window_size = max(1, int(os.environ.get("CONTROL_PLANE_GATE_WINDOW_SIZE", "15")))
    runtime_dir = root / "runtime"
    matrix_report = _read_json(runtime_dir / "metrics" / "control_plane_matrix_report.json")
    summaries = _collect_execution_summaries(runtime_dir / "evidence")
    evidence_records = _collect_evidence_records(runtime_dir / "evidence")
    logs = _collect_event_logs(runtime_dir / "event_log")
    gate_summaries = summaries[:gate_window_size]
    gate_records = evidence_records[:gate_window_size]

    normalized_summaries = []
    for item in gate_summaries:
        cloned = dict(item)
        cloned["primary_failure_type"] = _normalize_summary_primary(summary=cloned, logs=logs)
        normalized_summaries.append(cloned)
    terminal_run_keys = {
        f"{str(item.get('workflow_id', '')).strip()}/{str(item.get('phase_id', '')).strip()}"
        for item in normalized_summaries
        if str(item.get("workflow_id", "")).strip() and str(item.get("phase_id", "")).strip()
    }

    primary_hit_rate = _calc_primary_hit_rate(matrix_report)
    terminal_rate, terminal_map = _calc_terminal_state_consistency(normalized_summaries)
    event_rate, event_details = _calc_event_completeness(logs, terminal_run_keys)
    unknown_rate = _calc_unknown_failure_rate(normalized_summaries)
    required_detail_missing_rate, required_detail_violations = _calc_required_test_failure_detail_missing_rate(gate_records)
    unknown_breakdown = _unknown_source_breakdown(normalized_summaries)

    all_history_normalized = []
    for item in summaries:
        cloned = dict(item)
        cloned["primary_failure_type"] = _normalize_summary_primary(summary=cloned, logs=logs)
        all_history_normalized.append(cloned)
    all_terminal_rate, all_terminal_map = _calc_terminal_state_consistency(all_history_normalized)
    all_unknown_rate = _calc_unknown_failure_rate(all_history_normalized)
    all_required_detail_missing_rate, all_required_detail_violations = _calc_required_test_failure_detail_missing_rate(
        evidence_records
    )
    event_type_counter = Counter(
        str(item.get("event_type", "")).strip()
        for events in logs.values()
        for item in events
        if str(item.get("event_type", "")).strip()
    )

    report = {
        "generated_at": datetime.now().isoformat(),
        "metrics": {
            "primary_failure_hit_rate": primary_hit_rate,
            "event_completeness_rate": event_rate,
            "terminal_state_consistency_rate": terminal_rate,
            "unknown_failure_rate": unknown_rate,
            "required_test_failure_detail_missing_rate": required_detail_missing_rate,
        },
        "metrics_all_history": {
            "terminal_state_consistency_rate": all_terminal_rate,
            "unknown_failure_rate": all_unknown_rate,
            "required_test_failure_detail_missing_rate": all_required_detail_missing_rate,
        },
        "gate_window": {
            "size": gate_window_size,
            "gate_summary_count": len(gate_summaries),
            "gate_evidence_count": len(gate_records),
            "all_summary_count": len(summaries),
            "all_evidence_count": len(evidence_records),
        },
        "terminal_state_map_by_primary": terminal_map,
        "terminal_state_map_by_primary_all_history": all_terminal_map,
        "event_type_distribution": dict(event_type_counter),
        "event_completeness_details": event_details,
        "unknown_source_breakdown": unknown_breakdown,
        "required_test_failure_detail_violations": required_detail_violations,
        "required_test_failure_detail_violations_all_history": all_required_detail_violations,
        "release_gate_thresholds": {
            "primary_failure_hit_rate_min": 1.0,
            "event_completeness_rate_min": 1.0,
            "terminal_state_consistency_rate_min": 1.0,
            "unknown_failure_rate_max": 0.0,
            "required_test_failure_detail_missing_rate_max": 0.0,
        },
    }
    output_path = runtime_dir / "metrics" / "control_plane_slo_report.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(output_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
