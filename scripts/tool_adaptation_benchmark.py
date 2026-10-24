from __future__ import annotations

import argparse
import json
from pathlib import Path

from quentin.benchmarks.tool_adaptation import run_benchmark


def main() -> int:
    p = argparse.ArgumentParser(description="Tool management & adaptation benchmark (tools/skills/plugins/memory)")
    p.add_argument("--repo-root", default=".", help="Repository root")
    p.add_argument(
        "--output",
        default="generated/benchmarks/tool_adaptation_benchmark_report.json",
        help="Output report path",
    )
    p.add_argument(
        "--previous",
        default="generated/benchmarks/tool_adaptation_benchmark_prev.json",
        help="Previous report path",
    )
    p.add_argument(
        "--history",
        default="generated/benchmarks/tool_adaptation_benchmark_history.jsonl",
        help="History jsonl path",
    )
    p.add_argument("--domain-bucket", default="global", help="Calibration domain bucket label")
    p.add_argument("--min-score", type=float, default=0.70, help="Minimum quality score threshold")
    p.add_argument("--moving-window", type=int, default=5, help="Trend guard moving-average window.")
    p.add_argument("--trend-drop-tolerance", type=float, default=0.05, help="Allowed drop below moving average.")
    p.add_argument("--ci-mode", action="store_true", help="Enable deterministic CI mode.")
    p.add_argument("--no-enforce-schema", action="store_true", help="Do not fail benchmark on schema validation.")
    p.add_argument("--case-timeout-ms", type=int, default=6500, help="Per-case timeout budget in milliseconds.")
    p.add_argument("--soft-timeouts", action="store_true", help="Timeouts only warn, not fail.")
    p.add_argument(
        "--schema-file",
        default="quentin/benchmarks/schemas/tool_adaptation_report.schema.json",
        help="JSON schema file path for strict report validation",
    )
    p.add_argument("--no-deterministic-fixtures", action="store_true", help="Disable deterministic benchmark fixture mode.")
    p.add_argument("--no-auto-tune-weights", action="store_true", help="Disable history-driven weight autotuning.")
    p.add_argument(
        "--trend-ndjson-output",
        default="generated/benchmarks/tool_adaptation_trend.ndjson",
        help="Append trend row to NDJSON file",
    )
    args = p.parse_args()

    report = run_benchmark(
        repo_root=Path(args.repo_root),
        output=Path(args.output),
        previous=Path(args.previous) if args.previous else None,
        history=Path(args.history) if args.history else None,
        min_score=float(args.min_score),
        domain_bucket=str(args.domain_bucket or "global"),
        moving_window=int(args.moving_window),
        trend_drop_tolerance=float(args.trend_drop_tolerance),
        ci_mode=bool(args.ci_mode),
        enforce_schema=not bool(args.no_enforce_schema),
        case_timeout_ms=int(args.case_timeout_ms),
        strict_timeouts=not bool(args.soft_timeouts),
        schema_file=Path(args.schema_file) if args.schema_file else None,
        deterministic_fixtures=not bool(args.no_deterministic_fixtures),
        trend_ndjson_output=Path(args.trend_ndjson_output) if args.trend_ndjson_output else None,
        auto_tune_weights=not bool(args.no_auto_tune_weights),
    )
    print(
        json.dumps(
            {
                "quality_score": report.get("quality_score"),
                "min_score": report.get("min_score"),
                "pass": report.get("pass"),
                "improved_vs_previous": report.get("improved_vs_previous"),
                "previous_score": report.get("previous_score"),
                "top_issue_keys": [str(x.get("key") or "") for x in (report.get("issues") or [])[:8]],
                "top_weaknesses": report.get("top_weaknesses"),
                "trend_guard": report.get("trend_guard"),
                "schema_ok": ((report.get("schema_validation") or {}).get("ok")),
                "timeout_summary": report.get("timeout_summary"),
                "regression": report.get("regression_explain"),
                "remediation_queue_size": len(report.get("remediation_queue") or []),
                "replay": report.get("replay"),
                "weight_tuning": report.get("weight_tuning"),
            },
            ensure_ascii=False,
        )
    )
    return 0 if bool(report.get("pass")) else 2


if __name__ == "__main__":
    raise SystemExit(main())
