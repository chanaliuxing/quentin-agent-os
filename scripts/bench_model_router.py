#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path
from typing import Any, Dict

from quentin.routing.model_router import ModelRouter


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Micro-benchmark: ModelRouter.choose_model latency.")
    p.add_argument("--repo-root", default=".", help="Repo root (default: .)")
    p.add_argument("--rules-path", default="config/model_router_rules.json", help="Rules JSON path.")
    p.add_argument("--iters", type=int, default=2000, help="Iterations (default: 2000)")
    p.add_argument("--out", default="", help="Optional JSON output path (default: none)")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = Path(args.repo_root).resolve()
    rules_path = (repo_root / args.rules_path).resolve() if not Path(args.rules_path).is_absolute() else Path(args.rules_path)

    # Ensure deterministic behavior.
    os.environ.setdefault("LLM_MODEL", "qwen3-vl:latest")

    router = ModelRouter(repo_root=repo_root, rules_path=rules_path)

    iters = max(1, int(args.iters))
    start = time.perf_counter()
    for i in range(iters):
        pref = "balanced" if (i % 2 == 0) else "cost"
        router.choose_model(task_type="chat", domain="general", preference=pref)
    dur_s = max(1e-9, time.perf_counter() - start)

    result: Dict[str, Any] = {
        "benchmark": "model_router.choose_model",
        "iters": iters,
        "duration_ms": dur_s * 1000.0,
        "avg_us": (dur_s / iters) * 1_000_000.0,
        "rules_path": str(rules_path),
    }

    if str(args.out).strip():
        out_path = Path(args.out).expanduser()
        if not out_path.is_absolute():
            out_path = (repo_root / out_path).resolve()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

