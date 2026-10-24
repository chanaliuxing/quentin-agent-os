#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

# Ensure repo root is on sys.path when running as a script (not `python -m ...`).
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from quentin.runtime.brain_daemon import brain_daemon_from_env


def main() -> int:
    p = argparse.ArgumentParser(description="Run the Quentin brain loop (CognitiveLoop + optional Sleep/Immune).")
    p.add_argument("--input-text", default="", help="Task input text to run each iteration.")
    p.add_argument("--from-queue", action="store_true", help="Pull tasks from TaskQueue instead of fixed --input-text.")
    p.add_argument("--worker-id", default=os.getenv("QUENTIN_WORKER_ID", "brain-worker"), help="Worker id used to claim queue tasks.")
    p.add_argument("--max-tasks", type=int, default=0, help="Max tasks when --from-queue (0 means forever).")
    p.add_argument("--max-iterations", type=int, default=1, help="0 means forever; default 1.")
    args = p.parse_args()

    daemon = brain_daemon_from_env()
    if args.from_queue:
        daemon.run_queue_forever(worker_id=args.worker_id, max_tasks=int(args.max_tasks))
        return 0

    if not args.input_text:
        raise SystemExit("missing --input-text (or use --from-queue)")
    if args.max_iterations == 1:
        out = daemon.run_once(input_text=args.input_text, metadata={"source": "run_brain_daemon"})
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 0

    daemon.run_forever(input_text=args.input_text, max_iterations=int(args.max_iterations))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
