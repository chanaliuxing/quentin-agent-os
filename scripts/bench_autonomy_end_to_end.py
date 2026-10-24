from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path
import tempfile
import sys
import asyncio

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from quentin.runtime.task_sources import run_task_sources_once
from quentin.runtime.brain_daemon import brain_daemon_from_env
from quentin.runtime.task_queue import TaskQueue, TaskQueueItem


def main() -> int:
    ap = argparse.ArgumentParser(description="Offline end-to-end autonomy benchmark (queue -> brain).")
    ap.add_argument("--max-tasks", type=int, default=10, help="Number of tasks to drain from queue.")
    ap.add_argument("--out", type=str, default="data/bench/autonomy_end_to_end.json", help="Output JSON path (ignored by git).")
    args = ap.parse_args()

    repo_root = Path(__file__).resolve().parents[1]
    out_path = (repo_root / args.out).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as td:
        qpath = Path(td) / "queue.jsonl"
        # Force deterministic offline run.
        os.environ["LLM_STUB"] = "1"
        os.environ["QUENTIN_TASK_QUEUE_PATH"] = str(qpath)
        os.environ["QUENTIN_TASK_SOURCE_BLUEPRINT"] = "1"
        os.environ["QUENTIN_TASK_SOURCE_PATCHFLOW"] = "0"

        src_start = time.perf_counter()
        src_report = asyncio.run(
            run_task_sources_once(repo_root=str(repo_root), max_blueprint_tasks=max(int(args.max_tasks), 1))
        )
        src_ms = (time.perf_counter() - src_start) * 1000

        # Ensure the benchmark always has work to drain (task sources may legitimately enqueue 0).
        if int(src_report.enqueued) < int(args.max_tasks):
            q = TaskQueue(repo_root=str(repo_root))
            need = int(args.max_tasks) - int(src_report.enqueued)
            for i in range(max(0, need)):
                q.append(
                    TaskQueueItem.new(
                        input_text=f"[bench] filler task {i+1}/{need}",
                        domain="core",
                        environment="sandbox",
                        session_id="bench",
                        priority=0,
                        metadata={"source": "bench_autonomy_end_to_end", "kind": "filler"},
                    )
                )

        daemon = brain_daemon_from_env()
        wid = os.getenv("QUENTIN_WORKER_ID", "bench-worker")
        start = time.perf_counter()
        daemon.run_queue_forever(worker_id=wid, max_tasks=int(args.max_tasks))
        elapsed = time.perf_counter() - start

        out = {
            "mode": "offline",
            "max_tasks": int(args.max_tasks),
            "task_sources_ms": float(src_ms),
            "task_sources_enqueued": int(src_report.enqueued),
            "elapsed_sec": float(elapsed),
            "tasks_per_sec": float(int(args.max_tasks) / elapsed) if elapsed > 0 else 0.0,
            "queue_path": str(qpath),
        }
        out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(out, ensure_ascii=False, indent=2))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
