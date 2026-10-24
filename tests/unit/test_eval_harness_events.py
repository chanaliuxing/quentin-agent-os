from __future__ import annotations

import pytest

from quentin.infra.logging import Tracer
from quentin.infra.storage.kv_store import KVStore
from quentin.kernel.schemas import ExperimentVariant
from quentin.l3.research.eval_harness import EvalCase, EvalHarness
from quentin.runtime.system_events import SystemEventQueue


@pytest.mark.asyncio
async def test_eval_harness_emits_system_event_when_enabled(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("QUENTIN_EVAL_RESULTS_TO_EVENTS", "1")
    monkeypatch.setenv("QUENTIN_SESSION_ID", "eval-session")

    harness = EvalHarness(
        kv=KVStore(),
        tracer=Tracer(),
        repo_root=tmp_path,
        results_path=tmp_path / "eval_results.jsonl",
    )
    harness.register_evaluator(
        "router",
        lambda case, variant: {"output": case.input_payload.get("output", ""), "cost_tokens": 0.0, "latency_ms": 1.0},
    )

    variant = ExperimentVariant(variant_id="v1", name="router-a", target_type="router")
    case = EvalCase(case_id="c1", description="d", input_payload={"output": "ok"}, expected_keywords=["ok"])
    await harness.run_suite(experiment_id="exp_events", variant=variant, cases=[case])

    queue = SystemEventQueue(repo_root=tmp_path)
    events = queue.list_events(session_id="eval-session", limit=10)
    assert any(e.event_type == "evaluation_suite_completed" for e in events)

