from __future__ import annotations

from types import SimpleNamespace

from quentin.cognitive.loop_runtime_helpers import build_base_planner_context


def test_build_base_planner_context_includes_retry_error_patch_for_retry_attempt() -> None:
    class _Loop:
        def _compact_last_execution_for_planner(self, last_exec_result):  # type: ignore[no-untyped-def]
            _ = last_exec_result
            return {"ok": False}

        def _get_candidate_files(self, text):  # type: ignore[no-untyped-def]
            _ = text
            return ["a.py"]

    loop = _Loop()
    latest = SimpleNamespace(
        status="warning",
        failure_rate=0.5,
        consecutive_system_errors=0,
        consecutive_no_progress=0,
        failover_reason=None,
        anti_pattern_reason=None,
        last_error="",
        suggested_actions=[],
        to_dict=lambda: {"status": "warning"},
    )
    ctx = build_base_planner_context(
        loop=loop,
        task=SimpleNamespace(input_text="fix parser", metadata={}),
        historical_context="h",
        env_snapshot="tree",
        focus_paths_for_planner=["a.py"],
        last_exec_result={
            "raw": {"error": "TimeoutError: operation timed out"},
            "attempt_evaluation": {"category": "environment_timeout_error"},
        },
        last_plan_result=None,
        latest_self_awareness=latest,
        perception_data={},
        event_hint="",
        forbidden_actions=[],
        critical_instruction="",
        attempt_index=2,
        failure_count=1,
        tool_only_no_update_count=0,
        retry_budget_remaining=3.0,
    )
    assert "RETRY ERROR PATCH" in str(ctx.get("retry_error_patch") or "")
    assert "previous_error" in ctx
    strategy_patch = ctx.get("planning_strategy_patch") or {}
    assert strategy_patch.get("category") == "environment_timeout_error"
    assert "PLANNING STRATEGY PATCH" in str(ctx.get("planning_strategy_patch_text") or "")


def test_build_base_planner_context_includes_retry_plan_delta_patch() -> None:
    class _Loop:
        def _compact_last_execution_for_planner(self, last_exec_result):  # type: ignore[no-untyped-def]
            _ = last_exec_result
            return {"ok": False}

        def _get_candidate_files(self, text):  # type: ignore[no-untyped-def]
            _ = text
            return ["a.py"]

    class _PlanResult:
        steps = [{"step_id": "s1", "description": "write file"}, {"step_id": "s2", "description": "verify"}]

    loop = _Loop()
    latest = SimpleNamespace(
        status="warning",
        failure_rate=0.5,
        consecutive_system_errors=0,
        consecutive_no_progress=0,
        failover_reason=None,
        anti_pattern_reason=None,
        last_error="",
        suggested_actions=[],
        to_dict=lambda: {"status": "warning"},
    )
    ctx = build_base_planner_context(
        loop=loop,
        task=SimpleNamespace(input_text="fix parser", metadata={}),
        historical_context="h",
        env_snapshot="tree",
        focus_paths_for_planner=["a.py"],
        last_exec_result={
            "raw": {"error": "TimeoutError: operation timed out"},
            "attempt_evaluation": {"category": "environment_timeout_error"},
        },
        last_plan_result=_PlanResult(),
        latest_self_awareness=latest,
        perception_data={},
        event_hint="",
        forbidden_actions=[],
        critical_instruction="",
        attempt_index=2,
        failure_count=1,
        tool_only_no_update_count=0,
        retry_budget_remaining=3.0,
    )
    assert isinstance(ctx.get("retry_plan_delta"), dict)
    assert "RETRY PLAN DELTA" in str(ctx.get("retry_plan_delta_patch") or "")


def test_build_base_planner_context_includes_payload_variant() -> None:
    class _Loop:
        def _compact_last_execution_for_planner(self, last_exec_result):  # type: ignore[no-untyped-def]
            _ = last_exec_result
            return {"ok": False}

        def _get_candidate_files(self, text):  # type: ignore[no-untyped-def]
            _ = text
            return ["a.py"]

    loop = _Loop()
    latest = SimpleNamespace(
        status="warning",
        failure_rate=0.5,
        consecutive_system_errors=0,
        consecutive_no_progress=0,
        failover_reason=None,
        anti_pattern_reason=None,
        last_error="",
        suggested_actions=[],
        to_dict=lambda: {"status": "warning"},
    )
    ctx = build_base_planner_context(
        loop=loop,
        task=SimpleNamespace(input_text="fix parser", metadata={}),
        historical_context="h",
        env_snapshot="tree",
        focus_paths_for_planner=["a.py"],
        last_exec_result={
            "raw": {
                "error": "timeout",
                "steps": [{"result": {"call_tool": {"tool_name": "shell.run_command", "arguments": {"command": "ls"}}}}],
            },
            "attempt_evaluation": {"category": "environment_timeout_error"},
        },
        last_plan_result=None,
        latest_self_awareness=latest,
        perception_data={},
        event_hint="",
        forbidden_actions=[],
        critical_instruction="",
        attempt_index=2,
        failure_count=1,
        tool_only_no_update_count=0,
        retry_budget_remaining=3.0,
    )
    pv = ctx.get("planner_payload_variant") or {}
    assert pv.get("tool_family") == "shell"
    assert "PLANNER PAYLOAD VARIANT PATCH" in str(ctx.get("planner_payload_variant_patch") or "")
