import asyncio
import json

import pytest

from quentin.infra.logging import Tracer
from quentin.infra.storage.kv_store import KVStore
from quentin.kernel.schemas import ExperimentVariant
from quentin.l3.research.eval_harness import EvalHarness, EvalCase
from quentin.traces.core import JsonlTraceRecorder


@pytest.mark.asyncio
async def test_eval_harness_run_suite_persists(tmp_path):
    kv = KVStore()
    tracer = Tracer()
    recorder = JsonlTraceRecorder(repo_root=tmp_path)
    harness = EvalHarness(
        kv=kv,
        tracer=tracer,
        trace_recorder=recorder,
        results_path=tmp_path / "eval_results.jsonl",
    )

    harness.register_evaluator(
        "router",
        lambda case, variant: {"output": case.input_payload["output"], "cost_tokens": 1.0, "latency_ms": 5.0},
    )

    variant = ExperimentVariant(variant_id="v1", name="router-a", target_type="router")
    case = EvalCase(
        case_id="c1",
        description="check keyword",
        input_payload={"output": "hello world"},
        expected_keywords=["hello"],
    )

    suite = await harness.run_suite(experiment_id="exp1", variant=variant, cases=[case])

    assert suite.metrics["success_rate"] == 1.0
    assert suite.case_results[0].cost_tokens == 1.0

    # JSONL persisted
    lines = (tmp_path / "eval_results.jsonl").read_text(encoding="utf-8").strip().splitlines()
    assert lines and json.loads(lines[-1])["experiment_id"] == "exp1"

    # TraceRecorder received events
    events_path = tmp_path / "data" / "traces" / "events.jsonl"
    assert events_path.exists()
    assert '"task_result"' in events_path.read_text(encoding="utf-8")
