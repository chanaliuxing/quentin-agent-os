#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.metrics import (
    analyze_rolling_business_failure,
    create_taxonomy_ticket_if_needed,
    write_business_failure_monitor_report,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--window-size", type=int, default=20)
    parser.add_argument("--min-count", type=int, default=2)
    parser.add_argument("--min-ratio", type=float, default=0.05)
    parser.add_argument("--dedupe-hours", type=int, default=24)
    parser.add_argument("--include-non-real", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    analysis = analyze_rolling_business_failure(
        window_size=args.window_size,
        min_count=args.min_count,
        min_ratio=args.min_ratio,
        real_only=not args.include_non_real,
    )
    report_path = write_business_failure_monitor_report(analysis=analysis)
    ticket_path = create_taxonomy_ticket_if_needed(
        analysis=analysis,
        dedupe_hours=args.dedupe_hours,
    )
    print(report_path)
    if ticket_path:
        print(ticket_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
