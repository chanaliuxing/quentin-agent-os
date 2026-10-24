from __future__ import annotations

import json
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

from app.config import settings
from app.evidence import EvidenceStore
from app.metrics.runner_health import read_runner_health
from app.review import list_human_reviews


def build_system_hardening_report(
    *,
    runtime_dir: Path | None = None,
) -> dict[str, Any]:
    root = runtime_dir or settings.runtime_dir
    evidence_store = EvidenceStore(root / "evidence")
    records = [record for _, record in evidence_store.recent_records(limit=1000)]
    total = len(records)
    manual_interventions = len(list_human_reviews(root / "hooks"))
    signature_counter = Counter(record.failure_signature for record in records if record.failure_signature)
    failure_stage_counter = Counter(record.first_failure_stage for record in records if record.first_failure_stage)
    failure_owner_counter = Counter(record.owner_agent for record in records if record.owner_agent)
    failure_type_counter = Counter(record.failure_type for record in records if record.failure_type)
    unclassified_business_records = [
        record for record in records if str(record.failure_type).strip().upper() == "UNCLASSIFIED_BUSINESS_FAILURE"
    ]
    unclassified_business_stage_counter = Counter(
        str(record.first_failure_stage).strip() or "unknown_stage"
        for record in unclassified_business_records
    )
    unclassified_business_signature_counter = Counter(
        str(record.failure_signature).strip() or "unknown_signature"
        for record in unclassified_business_records
    )
    missing_artifact_counter = Counter(
        artifact
        for record in records
        for artifact in record.missing_artifacts
        if str(artifact).strip()
    )
    acceptance_counter = Counter(record.acceptance_status for record in records if record.acceptance_status)
    repeated_failures = sum(count for _, count in signature_counter.items() if count > 1)
    auto_resume_successes = sum(1 for record in records if record.acceptance_status == "passed")
    auto_resume_rate = auto_resume_successes / total if total else 0.0
    repeat_failure_rate = repeated_failures / total if total else 0.0
    manual_intervention_rate = manual_interventions / total if total else 0.0
    calibrated_policy = _load_json(settings.project_root / "policies" / "auto_review_policy.calibrated.json")
    runner_health = read_runner_health(runtime_dir=root)
    return {
        "generated_at": datetime.now().isoformat(),
        "sample_size": total,
        "manual_intervention_count": manual_interventions,
        "manual_intervention_rate": manual_intervention_rate,
        "auto_resume_success_count": auto_resume_successes,
        "auto_resume_success_rate": auto_resume_rate,
        "repeat_failure_signature_rate": repeat_failure_rate,
        "top_failure_signatures": signature_counter.most_common(5),
        "failure_stage_distribution": dict(failure_stage_counter),
        "failure_owner_distribution": dict(failure_owner_counter),
        "failure_type_distribution": dict(failure_type_counter),
        "top_failure_types": failure_type_counter.most_common(5),
        "unclassified_business_failure_count": len(unclassified_business_records),
        "unclassified_business_stage_distribution": dict(unclassified_business_stage_counter),
        "unclassified_business_top_signatures": unclassified_business_signature_counter.most_common(5),
        "missing_artifact_distribution": dict(missing_artifact_counter),
        "acceptance_distribution": dict(acceptance_counter),
        "calibrated_policy_active_profile": str(calibrated_policy.get("active_profile", "")),
        "calibrated_policy_sample_size": int(
            dict(calibrated_policy.get("calibration", {}) or {}).get("sample_size", 0)
        ),
        "runner_health": runner_health,
    }


def write_system_hardening_report(
    *,
    runtime_dir: Path | None = None,
    output_file: Path | None = None,
) -> Path:
    root = runtime_dir or settings.runtime_dir
    metrics_dir = root / "metrics"
    target = output_file or (metrics_dir / "system_hardening_report.json")
    previous = _load_json(target)
    report = build_system_hardening_report(runtime_dir=root)
    if previous:
        report["delta_vs_previous"] = _compute_delta(report, previous)
    else:
        report["delta_vs_previous"] = {}
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    history_dir = metrics_dir / "history"
    history_dir.mkdir(parents=True, exist_ok=True)
    history_file = history_dir / f"system_hardening_report_{datetime.now().strftime('%Y%m%d%H%M%S')}.json"
    history_file.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return target


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _compute_delta(current: dict[str, Any], previous: dict[str, Any]) -> dict[str, float]:
    numeric_fields = (
        "manual_intervention_rate",
        "auto_resume_success_rate",
        "repeat_failure_signature_rate",
    )
    delta: dict[str, float] = {}
    for field in numeric_fields:
        current_value = float(current.get(field, 0.0))
        previous_value = float(previous.get(field, 0.0))
        delta[field] = current_value - previous_value
    return delta
