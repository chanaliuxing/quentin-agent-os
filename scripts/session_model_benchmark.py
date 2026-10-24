from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from quentin.benchmarks.session_model import run_benchmark


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Session Model benchmark")
    parser.add_argument("--output", type=Path, default=Path("generated/benchmarks/session_model_benchmark_report.json"))
    args = parser.parse_args()

    report = run_benchmark(repo_root=REPO_ROOT)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"output": str(args.output), "quality_score": report.get("quality_score"), "pass": report.get("pass")}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
