from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict

from quentin.council.manager import CouncilDecision
from quentin.council.reflection import ReflectionCouncil


@dataclass
class _DummyGoal:
    id: str = "g1"
    title: str = "t"
    description: str = "d"
    domain: str = "core"
    metadata: Dict[str, Any] | None = None


class _CaptureManager:
    def __init__(self, final: Dict[str, Any]) -> None:
        self.final = final
        self.last_payload: Dict[str, Any] | None = None

    def run_council(self, council_name: str, question: Any) -> CouncilDecision:  # type: ignore[override]
        _ = council_name
        self.last_payload = question.payload
        return CouncilDecision(
            council_name="reflection",
            topic="reflection",
            final=self.final,
            member_replies=[],
            arbiter_raw=None,
            created_at="2026-02-10T00:00:00+00:00",
        )


def test_reflection_payload_is_compacted(monkeypatch) -> None:
    monkeypatch.setenv("QUENTIN_REFLECTION_MAX_TRACES", "2")
    monkeypatch.setenv("QUENTIN_REFLECTION_MAX_TRACE_STEPS", "1")
    monkeypatch.setenv("QUENTIN_REFLECTION_MAX_EXEC_STEPS", "1")
    monkeypatch.setenv("QUENTIN_REFLECTION_MAX_TEXT_CHARS", "20")
    monkeypatch.setenv("QUENTIN_REFLECTION_MAX_PLAN_RAW_CHARS", "30")

    mgr = _CaptureManager(final={"answer": {"action": "retry"}, "verdict": "ok", "reasoning": "r"})
    rc = ReflectionCouncil(council_manager=mgr)

    huge = "x" * 500
    rc.reflect(
        goal=_DummyGoal(),
        last_plan={"steps": [{"step_id": "s1", "description": huge}], "raw": huge},
        last_exec_result={
            "raw": {
                "success": False,
                "steps": [{"step_id": "e1", "description": huge, "result": huge, "error": huge}],
            },
            "final_output": huge,
            "actions_summary": huge,
        },
        metrics={"error_attempts": 1},
        failure_count=1,
        recent_traces=[
            {"attempt_index": 1, "steps": [{"step_id": "t1", "description": huge, "result": huge}]},
            {"attempt_index": 2, "steps": [{"step_id": "t2", "description": huge, "result": huge}]},
            {"attempt_index": 3, "steps": [{"step_id": "t3", "description": huge, "result": huge}]},
        ],
    )

    payload = mgr.last_payload or {}
    traces = payload.get("recent_traces") or []
    assert len(traces) == 2
    assert payload["last_execution"]["raw"]["steps_truncated"] is False
    assert payload["last_plan"]["raw"].endswith("...<truncated>")
    assert "...<truncated>" in payload["last_execution"]["final_output"]


def test_reflection_all_failed_degrades_to_abort() -> None:
    mgr = _CaptureManager(final={"verdict": "all_failed", "reasoning": "failed", "answer": {}})
    rc = ReflectionCouncil(council_manager=mgr)

    advice = rc.reflect(
        goal=_DummyGoal(),
        last_plan={},
        last_exec_result={},
        metrics={},
        failure_count=2,
    )

    assert advice.action == "abort"
    assert "failed" in advice.notes
    assert advice.summary == advice.notes


def test_reflection_parses_plain_action_string() -> None:
    mgr = _CaptureManager(final={"verdict": "ok", "reasoning": "r", "answer": "abort"})
    rc = ReflectionCouncil(council_manager=mgr)

    advice = rc.reflect(
        goal=_DummyGoal(),
        last_plan={},
        last_exec_result={},
        metrics={},
        failure_count=1,
    )

    assert advice.action == "abort"


def test_reflection_parses_json_in_prose_string() -> None:
    text = "I suggest this:\\n```json\\n{\"action\":\"request_skill\",\"skill_ideas\":[{\"name\":\"x\"}]}\\n```"
    mgr = _CaptureManager(final={"verdict": "ok", "reasoning": "r", "answer": text})
    rc = ReflectionCouncil(council_manager=mgr)

    advice = rc.reflect(
        goal=_DummyGoal(),
        last_plan={},
        last_exec_result={},
        metrics={},
        failure_count=1,
    )

    assert advice.action == "request_skill"
    assert isinstance(advice.skill_ideas, list) and len(advice.skill_ideas) == 1


def test_reflection_stale_retry_breaker_adjusts_goal(monkeypatch) -> None:
    monkeypatch.setenv("QUENTIN_REFLECTION_STALE_RETRY_FAILCOUNT", "3")
    monkeypatch.setenv("QUENTIN_REFLECTION_ABORT_FAILCOUNT", "6")
    mgr = _CaptureManager(
        final={
            "verdict": "ok",
            "reasoning": "Analyze why previous attempt failed and diagnose root cause. Retry.",
            "answer": {"action": "retry"},
        }
    )
    rc = ReflectionCouncil(council_manager=mgr)

    advice = rc.reflect(
        goal=_DummyGoal(),
        last_plan={"steps": []},
        last_exec_result={"final_output": "error: repeated_tool_call_loop"},
        metrics={"error_attempts": 4},
        failure_count=4,
        recent_traces=[],
    )

    assert advice.action == "adjust_goal"
    assert isinstance(advice.goal_adjustment, dict)
    assert advice.goal_adjustment.get("strategy") == "stale_retry_breaker"


def test_reflection_stale_retry_breaker_can_abort(monkeypatch) -> None:
    monkeypatch.setenv("QUENTIN_REFLECTION_STALE_RETRY_FAILCOUNT", "3")
    monkeypatch.setenv("QUENTIN_REFLECTION_ABORT_FAILCOUNT", "5")
    mgr = _CaptureManager(
        final={
            "verdict": "ok",
            "reasoning": "analyze root cause and retry",
            "answer": {"action": "retry"},
        }
    )
    rc = ReflectionCouncil(council_manager=mgr)

    advice = rc.reflect(
        goal=_DummyGoal(),
        last_plan={"steps": []},
        last_exec_result={"final_output": "error: max_step_iterations_reached"},
        metrics={"error_attempts": 5},
        failure_count=5,
        recent_traces=[],
    )

    assert advice.action == "abort"
