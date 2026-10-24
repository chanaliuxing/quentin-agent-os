from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

from quentin.cognitive.loop import CognitiveLoop
from quentin.cognitive.self_awareness import SelfAwarenessSnapshot


def test_extract_attempt_metrics_merges_step_and_meta():
    start = datetime(2024, 1, 1, 0, 0, 0)
    end = start + timedelta(seconds=2)

    raw = {
        "steps": [
            {"result": {"meta": {"tokens": 3, "latency_ms": 400}}},
            {
                "started_at": start.isoformat(),
                "finished_at": (start + timedelta(seconds=1)).isoformat(),
                "result": {"meta": {"cost_tokens": 2}},
            },
        ],
        "meta": {"tokens_used": 1},
    }

    metrics = CognitiveLoop._extract_attempt_metrics(raw_exec_data=raw, attempt_start=start, attempt_end=end)
    assert metrics["cost_tokens"] == 6.0
    assert metrics["latency_ms"] >= 1400.0


def test_is_tool_only_no_update_true_when_tool_result_without_progress():
    raw = {
        "steps": [
            {
                "result": {
                    "status": "ok",
                    "call_tool": {"tool_name": "fs.read_file", "args": {"path": "a.py"}},
                    "tool_result": {"success": True},
                }
            }
        ]
    }
    assert CognitiveLoop._is_tool_only_no_update(raw_exec_data=raw, final_output="") is True


def test_is_tool_only_no_update_false_with_meaningful_progress():
    raw = {
        "steps": [
            {
                "result": {
                    "status": "ok",
                    "tool_result": {"success": True},
                }
            }
        ]
    }
    assert (
        CognitiveLoop._is_tool_only_no_update(
            raw_exec_data=raw,
            final_output="Updated parser and added tests; all checks passed.",
        )
        is False
    )


def test_build_planner_hints_includes_self_awareness_note() -> None:
    hints = CognitiveLoop._build_planner_hints(
        {"self_awareness_note": "status=warning; failure_rate=0.66"}
    )
    assert any("status=warning" in item for item in hints)


def test_self_awareness_controls_request_flush_on_context_overflow() -> None:
    snapshot = SelfAwarenessSnapshot(
        status="warning",
        failure_rate=0.5,
        total_attempts=2,
        error_attempts=1,
        consecutive_system_errors=0,
        degrade_mode=False,
        self_programming_enabled=True,
        last_error="maximum context length exceeded",
        failover_reason="context_overflow",
        anti_pattern_reason=None,
        recent_failover_reasons=["context_overflow"],
        consecutive_no_progress=0,
        suggested_actions=["trigger_compaction_and_trim_context"],
        generated_at="2026-02-10T00:00:00+00:00",
    )
    ctrl = CognitiveLoop._apply_self_awareness_runtime_controls(snapshot)
    assert ctrl["request_flush"] is True
    assert ctrl["force_reflection"] is True
    assert ctrl["abort_now"] is False


def test_self_awareness_controls_abort_on_consecutive_critical_errors() -> None:
    snapshot = SelfAwarenessSnapshot(
        status="critical",
        failure_rate=1.0,
        total_attempts=3,
        error_attempts=3,
        consecutive_system_errors=2,
        degrade_mode=True,
        self_programming_enabled=False,
        last_error="executor crashed",
        failover_reason="timeout",
        anti_pattern_reason=None,
        recent_failover_reasons=["timeout", "timeout"],
        consecutive_no_progress=0,
        suggested_actions=["escalate_to_reflection_or_abort"],
        generated_at="2026-02-10T00:00:00+00:00",
    )
    ctrl = CognitiveLoop._apply_self_awareness_runtime_controls(snapshot)
    assert ctrl["abort_now"] is True
    assert "consecutive_system_errors=2" in str(ctrl["abort_reason"])


def test_self_awareness_controls_force_reflection_on_antipattern() -> None:
    snapshot = SelfAwarenessSnapshot(
        status="warning",
        failure_rate=0.5,
        total_attempts=2,
        error_attempts=1,
        consecutive_system_errors=0,
        degrade_mode=False,
        self_programming_enabled=True,
        last_error="Interactive command blocked",
        failover_reason=None,
        anti_pattern_reason="interactive_editor_command",
        recent_failover_reasons=[],
        consecutive_no_progress=1,
        suggested_actions=["switch_to_fs_read_and_write_flow"],
        generated_at="2026-02-10T00:00:00+00:00",
    )
    ctrl = CognitiveLoop._apply_self_awareness_runtime_controls(snapshot)
    assert ctrl["force_reflection"] is True


def test_detect_execution_antipattern_interactive_editor() -> None:
    raw = {
        "steps": [
            {
                "result": {
                    "call_tool": {
                        "tool_name": "shell.run_command",
                        "args": {"command": "cd quentin/infra/tools && nano ai_cli.py"},
                    }
                }
            }
        ]
    }
    signal = CognitiveLoop._detect_execution_antipattern(raw_exec_data=raw)
    assert signal["detected"] is True
    assert signal["reason"] == "interactive_editor_command"
    assert signal["target_path"] == "quentin/infra/tools/ai_cli.py"


def test_detect_execution_antipattern_from_feedback_tail() -> None:
    raw = {
        "steps": [
            {
                "result": {
                    "status": "error",
                    "feedback_tail": [
                        {
                            "tool_call": {
                                "tool_name": "shell.run_command",
                                "args": {"command": "cd quentin/infra/tools && nano ai_cli.py"},
                            },
                            "tool_result": {"status": "error", "error": "Interactive command 'nano' detected"},
                        }
                    ],
                }
            }
        ]
    }
    signal = CognitiveLoop._detect_execution_antipattern(raw_exec_data=raw)
    assert signal["detected"] is True
    assert signal["reason"] == "interactive_editor_command"


def test_build_antipattern_recovery_plan_prefers_fs_tools() -> None:
    task = type("Task", (), {"task_id": "t1"})()
    plan = CognitiveLoop._build_antipattern_recovery_plan(
        task=task,
        anti_pattern={"reason": "interactive_editor_command", "target_path": "a/b.py"},
    )
    steps = plan.get("steps") or []
    assert len(steps) == 3
    assert "fs.read_file" in str(steps[0].get("description") or "")
    assert "fs.search_replace" in str(steps[1].get("description") or "")
    assert "no_wget_no_nano_no_vim" == str(steps[2].get("notes") or "")


def test_build_antipattern_recovery_plan_for_dead_loop_starts_with_diagnostics() -> None:
    task = type("Task", (), {"task_id": "t1"})()
    plan = CognitiveLoop._build_antipattern_recovery_plan(
        task=task,
        anti_pattern={"reason": "repeated_tool_call_loop", "target_path": "extensions/tools/xh_leads"},
    )
    steps = plan.get("steps") or []
    assert len(steps) == 3
    assert "pwd" in str(steps[0].get("description") or "").lower()
    assert "fs.get_write_policy" in str(steps[1].get("description") or "")
    assert "gemini.code" in str(steps[2].get("description") or "")


def test_get_candidate_files_returns_relevant_paths(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    (repo / "quentin" / "infra" / "tools").mkdir(parents=True, exist_ok=True)
    (repo / "quentin" / "infra" / "tools" / "ai_cli.py").write_text("def run_cli():\n    return 'ok'\n", encoding="utf-8")
    (repo / "quentin" / "memory").mkdir(parents=True, exist_ok=True)
    (repo / "quentin" / "memory" / "fabric.py").write_text("class MemoryFabric:\n    pass\n", encoding="utf-8")

    loop = CognitiveLoop.__new__(CognitiveLoop)
    loop.repo_root = repo  # type: ignore[attr-defined]
    candidates = loop._get_candidate_files("fix ai cli tool wrapper", max_files=5)
    assert any("ai_cli.py" in p for p in candidates)


def test_get_candidate_files_prioritizes_explicit_root_file_mentions(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir(parents=True, exist_ok=True)
    (repo / "AGENTS.md").write_text("rules", encoding="utf-8")
    (repo / "pyproject.toml").write_text("[project]\nname='repo'\n", encoding="utf-8")
    (repo / "quentin" / "cognitive" / "perception").mkdir(parents=True, exist_ok=True)
    (repo / "quentin" / "cognitive" / "perception" / "instruction_booster.py").write_text("class X: pass\n", encoding="utf-8")

    loop = CognitiveLoop.__new__(CognitiveLoop)
    loop.repo_root = repo  # type: ignore[attr-defined]

    candidates = loop._get_candidate_files(
        "Inspect AGENTS.md and pyproject.toml, then create generated/brain_real_run_report.txt",
        max_files=5,
    )

    assert candidates[:2] == ["AGENTS.md", "pyproject.toml"]


def test_build_planner_hints_includes_candidate_files() -> None:
    hints = CognitiveLoop._build_planner_hints(
        {"candidate_files": ["quentin/infra/tools/ai_cli.py", "quentin/tools/manager.py"]}
    )
    assert any("Candidate files:" in h for h in hints)


def test_build_planner_hints_includes_forbidden_actions() -> None:
    hints = CognitiveLoop._build_planner_hints({"forbidden_actions": ["nano", "wget"]})
    assert any("Forbidden actions from recent guard feedback" in h for h in hints)


def test_build_planner_hints_includes_strategy_patch() -> None:
    hints = CognitiveLoop._build_planner_hints(
        {
            "planning_strategy_patch": {
                "category": "environment_timeout_error",
                "directives": ["switch to low-cost diagnostics"],
            }
        }
    )
    assert any("Planning strategy patch category" in h for h in hints)


def test_build_planner_hints_includes_retry_plan_delta() -> None:
    hints = CognitiveLoop._build_planner_hints({"retry_plan_delta": {"previous_step_count": 3}})
    assert any("Retry plan delta required" in h for h in hints)


def test_build_planner_hints_includes_payload_variant() -> None:
    hints = CognitiveLoop._build_planner_hints(
        {
            "planner_payload_variant": {
                "variant_id": "pv_retry_shell_timeout_v1",
                "directives": ["Shell-failure mode"],
            }
        }
    )
    assert any("Planner payload variant id" in h for h in hints)


def test_build_planner_hints_includes_intelligence_strict_reasons(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "QUENTIN_DONE_COUNCIL_STRICT_REASONS",
        "blocked_action_repeat_high,guardrail_tuning_summary_worsening",
    )
    hints = CognitiveLoop._build_planner_hints({})
    assert any("INTELLIGENCE STRICT REASONS" in h for h in hints)
    assert any("blocked_action_repeat_high" in h for h in hints)


def test_build_planner_hints_includes_write_policy() -> None:
    hints = CognitiveLoop._build_planner_hints({})
    assert any("WRITE POLICY: Allowed write roots are" in h for h in hints)


def test_repair_plan_quality_injects_speculative_probe_on_stuck_mode() -> None:
    loop = CognitiveLoop.__new__(CognitiveLoop)
    steps, notes = loop._repair_plan_quality(  # type: ignore[attr-defined]
        task_text="fix loop",
        context={"planner_lifecycle_payload": {"stage": "stuck"}},
        steps=[{"step_id": "s1", "description": "write file quickly", "skill_id": None}],
    )
    joined = " ".join([str(s.get("description") or "").lower() for s in steps])
    assert "speculative" in joined or "hypotheses" in joined
    step_notes = [str(s.get("notes") or "") for s in steps]
    assert any("speculative_probe" in n for n in notes + step_notes)


def test_repair_plan_quality_injects_progress_sync_when_forced() -> None:
    loop = CognitiveLoop.__new__(CognitiveLoop)
    steps, notes = loop._repair_plan_quality(  # type: ignore[attr-defined]
        task_text="long refactor",
        context={"planner_lifecycle_payload": {"stage": "stuck", "force_progress_sync": True}},
        steps=[{"step_id": "s1", "description": "apply patch", "skill_id": None}],
    )
    joined = " ".join([str(s.get("description") or "").lower() for s in steps])
    assert "progress" in joined
    assert ("inject_progress_sync_step" in notes) or ("decompose_single_step_fallback" in notes)


def test_should_trigger_reflection_respects_severity_and_budget() -> None:
    loop = CognitiveLoop.__new__(CognitiveLoop)
    should = loop._should_trigger_reflection(  # type: ignore[attr-defined]
        goal=SimpleNamespace(goal_id="g1"),
        metrics={"last_attempt_evaluation": {"severity": "critical"}, "retry_budget_remaining": 0.8},
        failure_count=1,
    )
    assert should is True


def test_build_executor_prompt_context_includes_intelligence_strict_reasons(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("QUENTIN_DONE_COUNCIL_STRICT_REASONS", "blocked_action_repeat_high")
    monkeypatch.setattr(CognitiveLoop, "_prompt_factory_enabled", staticmethod(lambda: True))
    loop = CognitiveLoop.__new__(CognitiveLoop)
    loop.repo_root = tmp_path  # type: ignore[attr-defined]
    task = SimpleNamespace(task_id="t1", metadata={})
    goal = SimpleNamespace(goal_id="g1", metadata={})
    ctx = loop._build_executor_prompt_context(  # type: ignore[attr-defined]
        task=task,
        goal=goal,
        progressive_pressure=False,
    )
    assert "INTELLIGENCE STRICT REASONS" in str(ctx.get("skill_prompt") or "")


def test_build_executor_prompt_context_exposes_strict_reasons_when_factory_disabled(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("QUENTIN_DONE_COUNCIL_STRICT_REASONS", "blocked_action_repeat_high")
    monkeypatch.setattr(CognitiveLoop, "_prompt_factory_enabled", staticmethod(lambda: False))
    loop = CognitiveLoop.__new__(CognitiveLoop)
    loop.repo_root = tmp_path  # type: ignore[attr-defined]
    task = SimpleNamespace(task_id="t1", metadata={})
    goal = SimpleNamespace(goal_id="g1", metadata={})
    ctx = loop._build_executor_prompt_context(  # type: ignore[attr-defined]
        task=task,
        goal=goal,
        progressive_pressure=False,
    )
    assert list(ctx.get("strict_reasons") or []) == ["blocked_action_repeat_high"]


def test_progressive_pressure_injected_after_three_tool_only_turns() -> None:
    count = 0
    samples = [
        {
            "steps": [
                {
                    "result": {
                        "status": "ok",
                        "call_tool": {"tool_name": "fs.read_file", "args": {"path": "a.py"}},
                        "tool_result": {"success": True},
                    }
                }
            ]
        },
        {
            "steps": [
                {
                    "result": {
                        "status": "ok",
                        "call_tool": {"tool_name": "shell.run_command", "args": {"command": "ls"}},
                        "tool_result": {"success": True},
                    }
                }
            ]
        },
        {
            "steps": [
                {
                    "result": {
                        "status": "ok",
                        "call_tool": {"tool_name": "fs.search_replace", "args": {"path": "a.py"}},
                        "tool_result": {"success": True},
                    }
                }
            ]
        },
    ]
    for raw in samples:
        if CognitiveLoop._is_tool_only_no_update(raw_exec_data=raw, final_output=""):
            count += 1
        else:
            count = 0
    assert count >= 3
    assert (count >= 3) is True


def test_progressive_pressure_resets_after_user_visible_update() -> None:
    count = 0
    first = {
        "steps": [
            {
                "result": {
                    "status": "ok",
                    "call_tool": {"tool_name": "fs.read_file", "args": {"path": "a.py"}},
                    "tool_result": {"success": True},
                }
            }
        ]
    }
    second = {
        "steps": [
            {
                "result": {
                    "status": "ok",
                    "call_tool": {"tool_name": "fs.search_replace", "args": {"path": "a.py"}},
                    "tool_result": {"success": True},
                }
            }
        ]
    }
    if CognitiveLoop._is_tool_only_no_update(raw_exec_data=first, final_output=""):
        count += 1
    if CognitiveLoop._is_tool_only_no_update(raw_exec_data=second, final_output=""):
        count += 1
    assert count == 2

    # User-visible update should reset no-progress streak.
    if CognitiveLoop._is_tool_only_no_update(
        raw_exec_data=second,
        final_output="Updated parser and verified syntax.",
    ):
        count += 1
    else:
        count = 0
    assert count == 0


def test_repair_plan_quality_injects_discovery_precheck(tmp_path: Path) -> None:
    loop = CognitiveLoop.__new__(CognitiveLoop)
    loop.repo_root = tmp_path  # type: ignore[attr-defined]
    repaired, notes = loop._repair_plan_quality(  # type: ignore[attr-defined]
        task_text="fix parser",
        context={},
        steps=[{"step_id": "s1", "description": "Write file using fs.write_file", "skill_id": None}],
    )
    assert repaired
    assert "Discovery precheck" in str(repaired[0].get("description") or "")
    assert (
        "inject_discovery_precheck" in notes
        or "decompose_single_step_fallback" in notes
    )


def test_repair_plan_quality_injects_strategy_patch_prechecks(tmp_path: Path) -> None:
    loop = CognitiveLoop.__new__(CognitiveLoop)
    loop.repo_root = tmp_path  # type: ignore[attr-defined]
    repaired, notes = loop._repair_plan_quality(  # type: ignore[attr-defined]
        task_text="fix timeout loop",
        context={
            "planner_lifecycle_payload": {"stage": "retry"},
            "planning_strategy_patch": {
                "category": "environment_timeout_error",
                "required_prechecks": ["timeout_probe", "env_diagnostics"],
            },
        },
        steps=[
            {"step_id": "s1", "description": "Apply direct file patch", "skill_id": None},
            {"step_id": "s2", "description": "Run verification", "skill_id": None},
        ],
    )
    joined = " ".join([str(s.get("description") or "").lower() for s in repaired])
    assert "strategy patch prechecks" in joined
    assert "inject_strategy_patch_prechecks" in notes


def test_repair_plan_quality_reuses_previous_plan_when_single_step_regresses(tmp_path: Path) -> None:
    loop = CognitiveLoop.__new__(CognitiveLoop)
    loop.repo_root = tmp_path  # type: ignore[attr-defined]
    previous = [
        {"step_id": "s1", "description": "discover files"},
        {"step_id": "s2", "description": "apply patch"},
        {"step_id": "s3", "description": "verify"},
    ]
    repaired, notes = loop._repair_plan_quality(  # type: ignore[attr-defined]
        task_text="fix parser",
        context={"previous_plan_steps": previous},
        steps=[{"step_id": "s1", "description": "just do everything"}],
    )
    assert len(repaired) >= 3
    assert "prevent_strategy_regression_reused_previous_decomposition" in notes


def test_repair_plan_quality_normalizes_tool_intent_and_verify_note(tmp_path: Path) -> None:
    loop = CognitiveLoop.__new__(CognitiveLoop)
    loop.repo_root = tmp_path  # type: ignore[attr-defined]
    repaired, notes = loop._repair_plan_quality(  # type: ignore[attr-defined]
        task_text="fix parser",
        context={},
        steps=[
            {
                "step_id": "s1",
                "description": "Run verification checks on changed file",
                "skill_id": None,
                "notes": "",
            }
        ],
    )
    assert repaired
    ti = repaired[0].get("tool_intent") if isinstance(repaired[0].get("tool_intent"), dict) else {}
    assert "expected_tool" in ti
    assert isinstance(ti.get("allowed_fallback_families"), list)
    assert "verify_condition:" in str(repaired[0].get("notes") or "")


def test_assess_discovery_guard_detects_missing_precheck(tmp_path: Path) -> None:
    loop = CognitiveLoop.__new__(CognitiveLoop)
    loop.repo_root = tmp_path  # type: ignore[attr-defined]
    guard = loop._assess_discovery_guard(  # type: ignore[attr-defined]
        [
            {"step_id": "s1", "description": "write file using fs.write_file"},
            {"step_id": "s2", "description": "verify"},
        ]
    )
    assert guard["risky_steps"] == 1
    assert guard["discovery_before_risky"] is False
