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


def _required_detail_stats(records: list[dict]) -> dict:
    target = [
        item
        for item in records
        if str(item.get("primary_failure_type", "")).strip().upper() == "REQUIRED_TEST_FAILED"
    ]
    if not target:
        return {
            "required_test_failed_runs": 0,
            "missing_detail_runs": 0,
            "required_test_failure_detail_missing_rate": 0.0,
            "violations": [],
        }

    violations = []
    for item in target:
        failed_tests = [str(x).strip() for x in item.get("failed_required_tests", []) if str(x).strip()]
        details_map = item.get("required_test_failure_details", {}) or {}
        missing = [
            test_name
            for test_name in failed_tests
            if not _has_required_test_detail_contract(
                test_name=test_name,
                details=list(details_map.get(test_name, []) or []),
            )
        ]
        if missing:
            violations.append(
                {
                    "run_id": str(item.get("run_id", "")),
                    "phase_id": str(item.get("phase_id", "")),
                    "missing_tests": sorted(set(missing)),
                }
            )
    return {
        "required_test_failed_runs": len(target),
        "missing_detail_runs": len(violations),
        "required_test_failure_detail_missing_rate": round(len(violations) / len(target), 4),
        "violations": violations,
    }


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    evidence_root = root / "runtime" / "evidence"
    records = _collect_evidence_records(evidence_root)
    recent_window_size = 20
    recent_records = records[:recent_window_size]
    recent_prefix = "required-detail-check-"
    recent_new_records = [item for item in records if str(item.get("run_id", "")).startswith(recent_prefix)][:20]

    report = {
        "generated_at": datetime.now().isoformat(),
        "windows": {
            "all_history": _required_detail_stats(records),
            f"latest_{recent_window_size}_records": _required_detail_stats(recent_records),
            f"latest_{recent_window_size}_{recent_prefix.rstrip('-')}": _required_detail_stats(recent_new_records),
        },
    }
    output_path = root / "runtime" / "metrics" / "control_plane_slo_split_report.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(output_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
