from __future__ import annotations

from datetime import datetime

from quentin.kernel.policy import ActionRequest
from quentin.council.manager import CouncilManager, CouncilQuestion
from quentin.routing.model_router import ModelRouter


def test_action_request_created_at_is_timezone_aware() -> None:
    action = ActionRequest.new(actor="test", action_type="tool_call")
    dt = datetime.fromisoformat(action.created_at)
    assert dt.tzinfo is not None


def test_model_router_usage_timestamp_is_timezone_aware() -> None:
    router = ModelRouter(base_config={"default_model": "qwen3-vl:latest"})
    router.record_usage("qwen3-vl:latest", tokens=10, latency_ms=3)
    ts = router.stats["qwen3-vl:latest"].last_called_at
    assert ts is not None
    assert ts.tzinfo is not None


def test_council_decision_created_at_is_timezone_aware(monkeypatch, tmp_path) -> None:
    manager = CouncilManager(repo_root=tmp_path)
    monkeypatch.setattr("quentin.council.manager.call_llm", lambda *a, **k: "{}")
    decision = manager.run_council(
        "planner",
        CouncilQuestion(
            topic="planner",
            importance="normal",
            prompt="quick check",
            payload={"goal": {"domain": "core", "environment": "sandbox"}},
        ),
    )
    dt = datetime.fromisoformat(decision.created_at)
    assert dt.tzinfo is not None
