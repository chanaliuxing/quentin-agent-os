from __future__ import annotations

import argparse
import json
import os
import sys
import asyncio

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from quentin.runtime.task_sources import run_task_sources_once


def main() -> int:
    ap = argparse.ArgumentParser(description="Run task sources once and enqueue tasks.")
    ap.add_argument("--repo-root", default=".", help="Repo root (default: .)")
    ap.add_argument("--max-blueprint-tasks", type=int, default=25, help="Max blueprint gap tasks to enqueue.")
    args = ap.parse_args()

    r = asyncio.run(run_task_sources_once(repo_root=args.repo_root, max_blueprint_tasks=int(args.max_blueprint_tasks)))
    print(json.dumps(r.to_dict(), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
