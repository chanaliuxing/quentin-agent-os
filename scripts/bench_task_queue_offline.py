#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path

from quentin.runtime.task_queue import TaskQueue, TaskQueueItem
from quentin.runtime.brain_daemon import brain_daemon_from_env


def main() -> int:
    p = argparse.ArgumentParser(description="Offline benchmark: enqueue N tasks, run queue with LLM_STUB=1.")
    p.add_argument("--n", type=int, default=50, help="number of tasks")
    p.add_argument("--out", default="data/bench/task_queue_offline.json", help="output json path (under data/ by default)")
    args = p.parse_args()

    # Ensure offline deterministic behavior unless user overrides.
    os.environ.setdefault("LLM_STUB", "1")

    out_path = Path(args.out).expanduser()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    q = TaskQueue(repo_root=".")
    for i in range(int(args.n)):
        q.append(TaskQueueItem.new(input_text=f"bench task {i}", metadata={"bench": True, "i": i}))

    daemon = brain_daemon_from_env()
    t0 = time.perf_counter()
    daemon.run_queue_forever(worker_id="bench-worker", max_tasks=int(args.n))
    dt = time.perf_counter() - t0

    rec = {"n": int(args.n), "total_sec": float(dt), "tasks_per_sec": (float(args.n) / dt) if dt > 0 else None}
    out_path.write_text(json.dumps(rec, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(rec, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

