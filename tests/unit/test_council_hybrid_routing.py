from __future__ import annotations

from types import SimpleNamespace

from quentin.council.manager import CouncilManager, CouncilQuestion
from quentin.routing.model_router import ModelInfo, ModelRouter


class _CaptureRouter:
    def __init__(self) -> None:
        self.calls = []

    def route(self, *, mode: str = "", task_type: str = "generic"):  # type: ignore[override]
        self.calls.append({"mode": mode, "task_type": task_type})
        return SimpleNamespace(
            provider="ollama",
            name="qwen3-vl:latest",
            router_mode=mode,
            router_task_type=task_type,
        )


def test_council_routes_high_complexity_to_reasoning_heavy(monkeypatch, tmp_path) -> None:
    capture = _CaptureRouter()
    manager = CouncilManager(repo_root=tmp_path, model_router=capture)

    seen = {"task_type": ""}

    def _fake_call_llm(*args, **kwargs):  # type: ignore[no-untyped-def]
        seen["task_type"] = str((kwargs.get("action_metadata") or {}).get("router_task_type") or "")
        return "{}"

    monkeypatch.setattr("quentin.council.manager.call_llm", _fake_call_llm)

    question = CouncilQuestion(
        topic="planner",
        importance="high",
        prompt="Please do architecture refactor with security constraint and rollback strategy.",
        payload={"goal": {"domain": "core", "environment": "sandbox"}},
    )
    manager.run_council("planner", question)
    assert seen["task_type"] == "reasoning_heavy"


def test_simple_task_routes_to_small_model(monkeypatch, tmp_path) -> None:
    router = ModelRouter(
        repo_root=tmp_path,
        models={
            "small-local": ModelInfo(name="small-local", kind="ollama"),
            "big-remote": ModelInfo(name="big-remote", kind="openai"),
        },
    )
    monkeypatch.setenv("QUENTIN_LOW_TIER_MODEL", "small-local")
    monkeypatch.setenv("QUENTIN_HIGH_TIER_MODEL", "big-remote")

    assert router.choose_model(task_type="simple_edit", preference="balanced") == "small-local"
    assert router.choose_model(task_type="read_write_basic", preference="balanced") == "small-local"


def test_complex_task_routes_to_high_tier_model(monkeypatch, tmp_path) -> None:
    router = ModelRouter(
        repo_root=tmp_path,
        models={
            "small-local": ModelInfo(name="small-local", kind="ollama"),
            "big-remote": ModelInfo(name="big-remote", kind="openai"),
        },
    )
    monkeypatch.setenv("QUENTIN_LOW_TIER_MODEL", "small-local")
    monkeypatch.setenv("QUENTIN_HIGH_TIER_MODEL", "big-remote")
    assert router.choose_model(task_type="reasoning_heavy", preference="balanced") == "big-remote"


def test_repeated_small_model_failures_trigger_escalation(monkeypatch, tmp_path) -> None:
    capture = _CaptureRouter()
    manager = CouncilManager(repo_root=tmp_path, model_router=capture)
    monkeypatch.setenv("QUENTIN_HIGH_TIER_MODEL", "big-remote")
    monkeypatch.setenv("QUENTIN_COUNCIL_ESCALATE_AFTER", "2")

    seen = {"forced": False, "reason": "", "chain": []}
    state = {"n": 0}

    def _fake_call_llm(*args, **kwargs):  # type: ignore[no-untyped-def]
        state["n"] += 1
        md = kwargs.get("action_metadata") or {}
        if md.get("forced_model"):
            seen["forced"] = True
            seen["reason"] = str(md.get("escalation_reason") or "")
            seen["chain"] = list(md.get("fallback_chain") or [])
            return "{}"
        return "not-json"

    monkeypatch.setattr("quentin.council.manager.call_llm", _fake_call_llm)
    question = CouncilQuestion(
        topic="planner",
        importance="high",
        prompt="Refactor architecture with multi-step constraints and rollback strategy.",
        payload={"goal": {"domain": "core", "environment": "sandbox"}},
    )
    manager.run_council("planner", question)
    manager.run_council("planner", question)
    assert seen["forced"] is True
    assert seen["reason"] == "member_parse_error_streak"
    assert "reasoning_heavy" in seen["chain"]
