#!/usr/bin/env python3
from __future__ import annotations

import json
from collections import Counter
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "runtime"
EVIDENCE = RUNTIME / "evidence"
OUT = RUNTIME / "metrics" / "business_failure_source_report.json"

TARGET_TYPES = {
    "BUSINESS_REJECTION_UNMAPPED",
    "BUSINESS_EVIDENCE_MISSING",
    "UNCLASSIFIED_BUSINESS_FAILURE",
}


def _read_summary_files() -> list[dict]:
    rows: list[dict] = []
    for path in EVIDENCE.rglob("execution_summary.json"):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        payload["_path"] = str(path)
        rows.append(payload)
    return rows


def main() -> int:
    rows = _read_summary_files()
    type_counter = Counter()
    stage_counter = Counter()
    signature_counter = Counter()

    for row in rows:
        code = str(row.get("primary_failure_type", "")).strip().upper()
        if code not in TARGET_TYPES:
            continue
        type_counter[code] += 1
        stage_counter[str(row.get("first_failure_stage", "")).strip() or "unknown_stage"] += 1
        signature_counter[str(row.get("failure_signature", "")).strip() or "unknown_signature"] += 1

    report = {
        "generated_at": datetime.now().isoformat(),
        "sample_size": len(rows),
        "target_failure_counts": dict(type_counter),
        "stage_distribution": dict(stage_counter),
        "top_signatures": signature_counter.most_common(10),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(OUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
