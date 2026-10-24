from __future__ import annotations

import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from quentin.l3.research.interface import ResearchInterfaceV3
from quentin.loops.immune_loop import ImmuneLoop
from quentin.traces.execution_trace import ExecutionTraceStore, ExecutionTrace
from quentin.l3.research.experiments import ExperimentStore, ResearchManager


def _build_traces(*, component_id: str, n: int, error_rate: float, latency_ms: float = 10.0) -> List[Dict[str, Any]]:
    n = max(1, int(n))
    fails = int(round(float(error_rate) * n))
    fails = min(max(fails, 0), n)
    traces: List[Dict[str, Any]] = []
    for i in range(n):
        traces.append(
            {
                "component_id": component_id,
                "success": False if i < fails else True,
                "latency_ms": float(latency_ms),
            }
        )
    return traces


def main() -> None:
    repo_root = Path(__file__).resolve().parents[1]

    with tempfile.TemporaryDirectory(prefix="quentin_immune_fb_") as d:
        tmp = Path(d).resolve()
        kv_path = tmp / "kv_store.sqlite3"
        defaults_path = tmp / "immune_loop_config.json"

        # Keep research state isolated.
        os.environ["QUENTIN_KVSTORE_PATH"] = str(kv_path)
        os.environ["QUENTIN_IMMUNE_DEFAULTS_PATH"] = str(defaults_path)
        os.environ["QUENTIN_IMMUNE_DEFAULTS_ENABLE"] = "1"

        ri = ResearchInterfaceV3(repo_root=str(repo_root))
        exp = ri.create_experiment(
            {
                "name": "ImmuneLoopThresholds",
                "description": "Offline immune_loop threshold A/B -> promote -> runtime defaults",
                "target_type": "immune_loop",
                "metrics": ["success_rate"],
                "variants": [
                    {"variant_id": "strict", "name": "Strict", "params": {"error_rate_threshold": 0.25, "min_samples": 10}},
                    {"variant_id": "lenient", "name": "Lenient", "params": {"error_rate_threshold": 0.5, "min_samples": 10}},
                ],
            }
        )
        exp_id = str(exp.get("experiment_id") or exp.get("experimentId") or "")
        if not exp_id:
            raise RuntimeError(f"missing experiment_id in create_experiment response: {exp}")

        cases = [
            {
                "case_id": "should_flag_at_0_27",
                "description": "planner should be flagged at error_rate=0.27",
                "input_payload": {
                    "traces": _build_traces(component_id="planner", n=10, error_rate=0.27)
                    + _build_traces(component_id="executor", n=10, error_rate=0.0),
                    "expect": {"flagged_components": ["planner"], "unflagged_components": ["executor"]},
                },
                "expected_keywords": [],
                "pass_threshold": 1.0,
                "meta": {},
            },
            {
                "case_id": "should_not_flag_at_0_10",
                "description": "executor should not be flagged at error_rate=0.10",
                "input_payload": {
                    "traces": _build_traces(component_id="executor", n=10, error_rate=0.10),
                    "expect": {"flagged_components": [], "unflagged_components": ["executor"]},
                },
                "expected_keywords": [],
                "pass_threshold": 1.0,
                "meta": {},
            },
        ]

        run = ri.run_experiment(exp_id, cases=cases)
        decision = ri.decide_and_promote_variant(
            exp_id,
            promote_policy={
                "metric": "success_rate",
                "min_delta": 0.01,
                "apply": True,
                "human_approved": True,
                "rules_path": str(defaults_path),
            },
        )

        if not defaults_path.exists():
            raise RuntimeError("promotion did not write immune defaults config")

        if not (decision.get("ok", True) is True and decision.get("applied", False) is True):
            raise RuntimeError(f"promotion failed: {decision}")

        # Verify runtime defaults affect behavior when QUENTIN_IMMUNE_DEFAULTS_ENABLE=1.
        traces_root = tmp / "traces"
        traces_root.mkdir(parents=True, exist_ok=True)
        store = ExecutionTraceStore(repo_root=str(traces_root))
        now = datetime.now(timezone.utc).isoformat()
        # error_rate=0.27 should be flagged with promoted threshold 0.25 (but NOT with default 0.30).
        for i, t in enumerate(_build_traces(component_id="planner", n=10, error_rate=0.27)):
            store.append(
                ExecutionTrace(
                    trace_id=f"t{i}",
                    task_id=f"task{i}",
                    component_id=str(t["component_id"]),
                    success=bool(t["success"]),
                    start_time=now,
                    end_time=now,
                    metrics={"latency_ms": float(t["latency_ms"])},
                )
            )

        rm = ResearchManager(store=ExperimentStore(repo_root=str(traces_root)))
        loop = ImmuneLoop(
            repo_root=str(traces_root),
            config=None,  # allow defaults file to apply
            traces_store=store,
            research_manager=rm,
            immune_cases_path="data/immune_cases.jsonl",
        )
        immune_cases = loop.run_once()
        flagged = {c.component_id for c in immune_cases}
        if "planner" not in flagged:
            raise RuntimeError(f"expected planner to be flagged via promoted defaults; flagged={sorted(flagged)}")

        print("OK: full L3->L2->L1 immune loop feedback loop completed.")
        print("experiment_id:", exp_id)
        print("run:", run.get("variant_results") or run.get("variant_results", {}))
        print("decision:", decision)


if __name__ == "__main__":
    main()
