#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.metrics import (
    analyze_subprocess_nonzero_exit,
    create_execution_remediation_ticket_if_needed,
    write_execution_remediation_report,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--window-size", type=int, default=20)
    parser.add_argument("--min-count", type=int, default=2)
    parser.add_argument("--min-ratio", type=float, default=0.2)
    parser.add_argument("--dedupe-hours", type=int, default=24)
    parser.add_argument("--include-non-real", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    analysis = analyze_subprocess_nonzero_exit(
        window_size=max(1, int(args.window_size)),
        min_count=max(1, int(args.min_count)),
        min_ratio=float(args.min_ratio),
        real_only=not bool(args.include_non_real),
    )
    report_path = write_execution_remediation_report(analysis=analysis)
    ticket_path = create_execution_remediation_ticket_if_needed(
        analysis=analysis,
        dedupe_hours=max(1, int(args.dedupe_hours)),
    )
    print(report_path)
    if ticket_path:
        print(ticket_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
