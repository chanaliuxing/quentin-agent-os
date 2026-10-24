from __future__ import annotations

import argparse
import json
import math
import random
import statistics
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from quentin.loops.immune_loop import ImmuneLoop, ImmuneConfig
from quentin.traces.execution_trace import ExecutionTrace, ExecutionTraceStore
from quentin.l3.research.experiments import ExperimentStore, ResearchManager


def _quantile(values: List[float], q: float) -> float:
    if not values:
        return 0.0
    xs = sorted(values)
    idx = int(math.ceil(q * len(xs))) - 1
    idx = min(max(idx, 0), len(xs) - 1)
    return float(xs[idx])


def _build_traces(*, component_id: str, n: int, error_rate: float, rng: random.Random) -> List[ExecutionTrace]:
    n = max(1, int(n))
    fails = int(round(float(error_rate) * n))
    fails = min(max(fails, 0), n)
    now = datetime.now(timezone.utc).isoformat()
    traces: List[ExecutionTrace] = []
    for i in range(n):
        success = False if i < fails else True
        latency_ms = float(rng.uniform(5.0, 50.0))
        traces.append(
            ExecutionTrace(
                trace_id=f"{component_id}:{i}",
                task_id=f"{component_id}:task:{i}",
                component_id=component_id,
                success=success,
                start_time=now,
                end_time=now,
                metrics={"latency_ms": latency_ms},
                tags={},
            )
        )
    return traces


def main() -> None:
    parser = argparse.ArgumentParser(description="ImmuneLoop micro-benchmark (run_once latency).")
    parser.add_argument("--components", type=int, default=10)
    parser.add_argument("--traces-per", type=int, default=50)
    parser.add_argument("--error-rate", type=float, default=0.2)
    parser.add_argument("--threshold", type=float, default=0.3)
    parser.add_argument("--min-samples", type=int, default=10)
    parser.add_argument("--runs", type=int, default=5)
    parser.add_argument("--seed", type=int, default=13)
    parser.add_argument("--out", default="data/bench/immune_loop_bench.jsonl")
    args = parser.parse_args()

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    rng = random.Random(int(args.seed))
    durations: List[float] = []
    num_cases: List[int] = []

    for _ in range(max(1, int(args.runs))):
        with tempfile.TemporaryDirectory(prefix="quentin_bench_immune_") as d:
            store = ExecutionTraceStore(repo_root=d)
            for c in range(max(1, int(args.components))):
                comp_id = f"comp_{c}"
                for tr in _build_traces(
                    component_id=comp_id,
                    n=int(args.traces_per),
                    error_rate=float(args.error_rate),
                    rng=rng,
                ):
                    store.append(tr)

            rm = ResearchManager(store=ExperimentStore(repo_root=d))
            loop = ImmuneLoop(
                repo_root=d,
                config=ImmuneConfig(
                    window_minutes=60,
                    min_samples=int(args.min_samples),
                    error_rate_threshold=float(args.threshold),
                    latency_ms_threshold=None,
                    enable_self_fix=False,
                    max_self_fix_per_run=0,
                    component_to_module={},
                ),
                traces_store=store,
                research_manager=rm,
                immune_cases_path="data/immune_cases.jsonl",
            )

            start = time.perf_counter()
            cases = loop.run_once()
            durations.append((time.perf_counter() - start) * 1000.0)
            num_cases.append(len(cases or []))

    result: Dict[str, Any] = {
        "components": int(args.components),
        "traces_per": int(args.traces_per),
        "total_traces": int(args.components) * int(args.traces_per),
        "error_rate": float(args.error_rate),
        "threshold": float(args.threshold),
        "min_samples": int(args.min_samples),
        "runs": int(args.runs),
        "avg_ms": round(statistics.mean(durations), 3) if durations else 0.0,
        "p95_ms": round(_quantile(durations, 0.95), 3) if durations else 0.0,
        "avg_num_cases": round(statistics.mean(num_cases), 3) if num_cases else 0.0,
        "recorded_at": time.time(),
    }

    with out_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(result, ensure_ascii=False) + "\n")

    print("Bench results (written to:", str(out_path) + ")")
    print(result)


if __name__ == "__main__":
    main()

