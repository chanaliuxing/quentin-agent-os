#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.metrics import write_agent_execution_failure_breakdown_report


def main() -> int:
    parser = argparse.ArgumentParser(description="Write rolling agent execution failure breakdown report.")
    parser.add_argument("--window-size", type=int, default=20)
    parser.add_argument("--include-non-real", action="store_true")
    args = parser.parse_args()

    report = write_agent_execution_failure_breakdown_report(
        window_size=max(1, int(args.window_size)),
        real_only=not bool(args.include_non_real),
    )
    print(report)
    payload = json.loads(report.read_text(encoding="utf-8"))
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
