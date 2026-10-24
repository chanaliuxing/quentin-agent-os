from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.config import settings
from app.evidence import EvidenceStore


def build_policy_tuning_dataset(*, runtime_dir: Path | None = None) -> dict[str, Any]:
    root = runtime_dir or settings.runtime_dir
    records = [record for _, record in EvidenceStore(root / "evidence").recent_records(limit=5000)]
    total = len(records)
    passed = sum(1 for item in records if item.acceptance_status == "passed")
    rejected = sum(1 for item in records if item.acceptance_status != "passed")
    by_owner: dict[str, int] = {}
    for item in records:
        owner = item.owner_agent or "unknown"
        by_owner[owner] = by_owner.get(owner, 0) + 1
    return {
        "sample_size": total,
        "passed_count": passed,
        "rejected_count": rejected,
        "owner_distribution": by_owner,
    }


def calibrate_auto_review_policy(
    *,
    policy_file: Path | None = None,
    runtime_dir: Path | None = None,
    output_file: Path | None = None,
) -> Path:
    root = runtime_dir or settings.runtime_dir
    source_policy_file = policy_file or (settings.project_root / "policies" / "auto_review_policy.json")
    output_policy_file = output_file or (settings.project_root / "policies" / "auto_review_policy.calibrated.json")
    dataset = build_policy_tuning_dataset(runtime_dir=root)
    source_policy = _load_json(source_policy_file)
    if not source_policy:
        source_policy = {"profiles": {}}

    sample_size = int(dataset.get("sample_size", 0))
    passed_ratio = float(dataset.get("passed_count", 0)) / sample_size if sample_size else 0.0
    target_profile = "strict" if passed_ratio < 0.2 else "normal"

    calibrated_policy = dict(source_policy)
    profiles = dict(calibrated_policy.get("profiles", {}) or {})
    normal = dict(profiles.get("normal", {}) or {})
    strict = dict(profiles.get("strict", {}) or {})
    normal_conf = dict(normal.get("confidence", {"approve": 0.9, "reject": 0.8}))
    strict_conf = dict(strict.get("confidence", {"approve": 0.95, "reject": 0.85}))

    if sample_size >= 5 and passed_ratio < 0.1:
        normal_conf["approve"] = min(0.99, float(normal_conf.get("approve", 0.9)) + 0.03)
        strict_conf["approve"] = min(0.995, float(strict_conf.get("approve", 0.95)) + 0.02)
    elif sample_size >= 5 and passed_ratio > 0.5:
        normal_conf["approve"] = max(0.7, float(normal_conf.get("approve", 0.9)) - 0.05)
        strict_conf["approve"] = max(0.75, float(strict_conf.get("approve", 0.95)) - 0.03)

    normal["confidence"] = normal_conf
    strict["confidence"] = strict_conf
    profiles["normal"] = normal
    profiles["strict"] = strict
    calibrated_policy["profiles"] = profiles
    calibrated_policy["active_profile"] = target_profile
    calibrated_policy["calibration"] = {
        "sample_size": sample_size,
        "passed_ratio": passed_ratio,
        "target_profile": target_profile,
    }

    output_policy_file.parent.mkdir(parents=True, exist_ok=True)
    output_policy_file.write_text(
        json.dumps(calibrated_policy, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    dataset_file = root / "metrics" / "policy_tuning_dataset.json"
    dataset_file.parent.mkdir(parents=True, exist_ok=True)
    dataset_file.write_text(json.dumps(dataset, ensure_ascii=False, indent=2), encoding="utf-8")
    return output_policy_file


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
