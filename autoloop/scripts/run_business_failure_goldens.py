#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.metrics import infer_taxonomy_candidate_name, normalize_business_failure_signature


def main() -> int:
    rows = []
    passed = 0
    total = 0
    golden_dirs = [
        ROOT_DIR / "tests" / "replay" / "business_failure_golden_pack",
        ROOT_DIR / "tests" / "replay" / "agent_execution_failure_golden_pack",
    ]
    for golden_dir in golden_dirs:
        if not golden_dir.exists():
            continue
        for path in sorted(golden_dir.glob("*.json")):
            payload = json.loads(path.read_text(encoding="utf-8"))
            actual_signature = normalize_business_failure_signature(
                primary_failure_type=str(payload.get("primary_failure_type", "")),
                first_failure_stage=str(payload.get("first_failure_stage", "")),
                missing_artifacts=[str(item) for item in payload.get("missing_artifacts", []) if str(item).strip()],
                grader_results={str(k): str(v) for k, v in dict(payload.get("grader_results", {}) or {}).items()},
                failure_events=[item for item in payload.get("failure_events", []) if isinstance(item, dict)],
            )
            actual_candidate = infer_taxonomy_candidate_name(
                signature=actual_signature,
                primary_failure_type=str(payload.get("primary_failure_type", "")),
            )
            expected_signature = str(payload.get("expected_signature", "")).strip().lower()
            expected_candidate = str(payload.get("expected_candidate_enum", "")).strip().upper()
            ok = actual_signature == expected_signature and actual_candidate == expected_candidate
            total += 1
            passed += int(ok)
            rows.append(
                {
                    "pack": golden_dir.name,
                    "file": str(path),
                    "pass": ok,
                    "expected_signature": expected_signature,
                    "actual_signature": actual_signature,
                    "expected_candidate_enum": expected_candidate,
                    "actual_candidate_enum": actual_candidate,
                }
            )
    report = {
        "generated_at": datetime.now().isoformat(),
        "total": total,
        "passed": passed,
        "pass_rate": round(passed / total, 4) if total else 1.0,
        "results": rows,
    }
    out = ROOT_DIR / "runtime" / "metrics" / "business_failure_goldens_report.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(out)
    if total and passed != total:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
