#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.config import settings
from app.metrics import infer_taxonomy_candidate_name, normalize_business_failure_signature


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--window-size", type=int, default=20)
    parser.add_argument("--promote-count", type=int, default=2)
    parser.add_argument("--real-only", action="store_true", default=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    rows = _collect_summaries(settings.runtime_dir / "evidence")
    if args.real_only:
        rows = [row for row in rows if _is_real_run(str(row.get("workflow_id", "")))]
    rows = sorted(rows, key=lambda item: float(item.get("_mtime", 0.0)), reverse=True)[: max(1, args.window_size)]
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        primary = str(row.get("primary_failure_type", "")).strip().upper()
        if primary not in {"BUSINESS_REJECTION_UNMAPPED", "BUSINESS_EVIDENCE_MISSING"}:
            continue
        signature = normalize_business_failure_signature(
            primary_failure_type=primary,
            first_failure_stage=str(row.get("first_failure_stage", "")),
            missing_artifacts=[str(item) for item in row.get("missing_artifacts", []) if str(item).strip()],
            grader_results={str(k): str(v) for k, v in dict(row.get("grader_results", {}) or {}).items()},
            failure_events=[item for item in row.get("failure_events", []) if isinstance(item, dict)],
        )
        grouped[signature].append(row)
    proposals = []
    for signature, items in sorted(grouped.items(), key=lambda pair: len(pair[1]), reverse=True):
        if len(items) < max(1, args.promote_count):
            continue
        primary = str(items[0].get("primary_failure_type", "")).strip().upper() or "BUSINESS_REJECTION_UNMAPPED"
        candidate = infer_taxonomy_candidate_name(signature=signature, primary_failure_type=primary)
        proposals.append(
            {
                "candidate_enum": candidate,
                "source_primary_failure_type": primary,
                "normalized_signature": signature,
                "occurrences": len(items),
                "sample_evidence_files": [str(item.get("_path", "")) for item in items[:3]],
                "recommended_playbook_action": (
                    "replan_from_spec" if "test" in signature or "grader" in signature else "taxonomy_review_required"
                ),
            }
        )
    failure_counts = Counter(str(item.get("primary_failure_type", "")).strip().upper() for item in rows)
    report = {
        "generated_at": datetime.now().isoformat(),
        "window_size": int(args.window_size),
        "evaluated_runs": len(rows),
        "failure_type_distribution": dict(failure_counts),
        "promotion_candidates": proposals,
    }
    out = settings.runtime_dir / "metrics" / "business_failure_promotion_report.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(out)
    return 0


def _collect_summaries(evidence_root: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not evidence_root.exists():
        return rows
    for path in evidence_root.rglob("execution_summary.json"):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        payload["_path"] = str(path)
        payload["_mtime"] = path.stat().st_mtime
        rows.append(payload)
    return rows


def _is_real_run(run_id: str) -> bool:
    normalized = str(run_id).strip().lower()
    return normalized.startswith(("real-", "prod-"))


if __name__ == "__main__":
    raise SystemExit(main())
