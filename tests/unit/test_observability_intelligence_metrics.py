import asyncio
import json
from pathlib import Path

from quentin.observability.service import ObservabilityService


def _write_jsonl(path: Path, rows) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def test_observability_intelligence_metrics(tmp_path: Path, monkeypatch) -> None:
    feedback_path = tmp_path / "data" / "metrics" / "vision_budget_feedback.jsonl"
    feedback_path.parent.mkdir(parents=True, exist_ok=True)
    feedback_path.write_text(
        json.dumps(
            {
                "timestamp": "2026-02-21T00:00:00+00:00",
                "domain": "web",
                "task_class": "debug_ui",
                "outcome_score": 0.9,
                "success": True,
                "budget": {"total_tokens": 5000, "screenshot_tokens": 3300, "ui_tree_tokens": 1100, "ocr_tokens": 600},
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("QUENTIN_VISION_BUDGET_FEEDBACK_PATH", str(feedback_path))

    events_path = tmp_path / "data" / "traces" / "events.jsonl"
    _write_jsonl(
        events_path,
        [
            {
                "trace_id": "t1",
                "event_type": "planning",
                "payload": {
                    "planner_repairs": ["inject_discovery_precheck"],
                    "discovery_guard": {"risky_steps": 1, "discovery_before_risky": True},
                    "context_injected": {
                        "planning_diagnostics": {
                            "payload_variant_id": "pv_retry_shell_environment_timeout_error_shell_timeout_v1",
                            "payload_tool_family": "shell",
                            "error_subcategory": "shell_timeout",
                            "strategy_patch_id": "timeout_diagnostics_v1",
                        }
                    },
                },
            },
            {
                "trace_id": "t2",
                "event_type": "planning",
                "payload": {
                    "planner_repairs": [],
                    "discovery_guard": {"risky_steps": 1, "discovery_before_risky": False},
                    "context_injected": {
                        "planning_diagnostics": {
                            "payload_variant_id": "pv_retry_browser_tool_execution_error_browser_selector_not_found_v1",
                            "payload_tool_family": "browser",
                            "error_subcategory": "browser_selector_not_found",
                            "strategy_patch_id": "tool_guardrails_v1",
                        }
                    },
                },
            },
            {
                "trace_id": "t3",
                "event_type": "planning",
                "payload": {
                    "planner_repairs": ["decompose_single_step_fallback"],
                    "discovery_guard": {"risky_steps": 0, "discovery_before_risky": True},
                },
            },
        ],
    )

    audit_path = tmp_path / "data" / "audit_events.jsonl"
    _write_jsonl(
        audit_path,
        [
            {
                "action_id": "a1",
                "event_type": "tool_call",
                "phase": "denied",
                "actor": "tool_manager",
                "payload": {"reason": "Interactive command 'nano' detected"},
            },
            {
                "action_id": "a2",
                "event_type": "tool_call",
                "phase": "denied",
                "actor": "tool_manager",
                "payload": {"reason": "Interactive command 'nano' detected"},
            },
            {
                "action_id": "a3",
                "event_type": "tool_call",
                "phase": "error",
                "actor": "tool_manager",
                "payload": {"reason": "blocked wget download"},
            },
            {
                "action_id": "dq1",
                "event_type": "done_council_quality",
                "phase": "weak_reasoning_detected",
                "actor": "done_council",
                "payload": {},
            },
            {
                "action_id": "dq2",
                "event_type": "done_council_quality",
                "phase": "retry_improved",
                "actor": "done_council",
                "payload": {},
            },
        ],
    )
    runtime_state_path = tmp_path / "data" / "runtime" / "brain_guardrail_state.json"
    runtime_state_path.parent.mkdir(parents=True, exist_ok=True)
    runtime_state_path.write_text(
        json.dumps(
            {
                "intelligence_recovery_outcomes": [True, False, True, False],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    queue_path = tmp_path / "data" / "tasks" / "queue.jsonl"
    _write_jsonl(
        queue_path,
        [
            {
                "task_id": "q1",
                "status": "done",
                "metadata": {"kind": "intelligence_regression_recovery", "recovery_focus": "guessing_trap"},
            },
            {
                "task_id": "q2",
                "status": "failed",
                "metadata": {"kind": "intelligence_regression_recovery", "recovery_focus": "guessing_trap"},
            },
            {
                "task_id": "q3",
                "status": "done",
                "metadata": {"kind": "intelligence_regression_recovery", "recovery_focus": "semantic_stagnation"},
            },
        ],
    )

    svc = ObservabilityService(runtime=None, repo_root=tmp_path)
    overview = asyncio.run(svc.get_overview())
    intel = overview["intelligence"]

    assert intel["planner_repairs"]["total_plans"] == 3
    assert intel["planner_repairs"]["plans_with_repairs"] == 2
    assert intel["planner_repairs"]["repair_reason_counts"]["inject_discovery_precheck"] == 1
    assert intel["planner_repairs"]["discovery_precheck"]["risky_plans"] == 2
    assert intel["planner_repairs"]["discovery_precheck"]["compliant_plans"] == 1
    assert intel["planning_diagnostics"]["payload_tool_family_counts"]["shell"] == 1
    assert intel["planning_diagnostics"]["payload_tool_family_counts"]["browser"] == 1
    assert intel["planning_diagnostics"]["error_subcategory_counts"]["shell_timeout"] == 1
    assert intel["planning_diagnostics"]["error_subcategory_counts"]["browser_selector_not_found"] == 1
    assert intel["planning_diagnostics"]["strategy_patch_counts"]["timeout_diagnostics_v1"] == 1
    assert intel["blocked_action_recurrence"]["blocked_total"] == 3
    assert intel["blocked_action_recurrence"]["blocked_repeated_total"] == 2
    assert intel["done_council_quality"]["weak_reasoning_detected"] == 1
    assert intel["done_council_quality"]["retry_improved"] == 1
    assert intel["recovery_loop"]["sample_size"] == 4
    assert intel["recovery_loop"]["success_rate"] == 0.5
    assert intel["recovery_loop"]["trend_window_size"] == 2
    assert intel["recovery_loop"]["prior_window_rate"] == 0.5
    assert intel["recovery_loop"]["recent_window_rate"] == 0.5
    assert intel["recovery_loop"]["trend_delta"] == 0.0
    focus = intel["recovery_loop"]["focus_breakdown"]
    assert len(focus) >= 2
    assert focus[0]["focus"] == "guessing_trap"
    assert focus[0]["total"] == 2
    assert focus[0]["success_rate"] == 0.5
    assert int(intel["vision_budget_feedback"]["total_rows"]) == 1
    assert float(intel["vision_budget_feedback"]["avg_effective_outcome_score"]) == 0.9
    assert float(intel["vision_budget_feedback"]["judge_signal_coverage"]) == 0.0
    audit = overview["intelligence_audit"]
    assert audit["guessing_trap"]["risky_without_discovery"] == 1
    assert audit["semantic_stagnation"]["weak_reasoning_detected"] == 1
    assert audit["strategy_regression"]["fallback_decompositions"] == 1
    assert audit["self_awareness_gap"]["blocked_action_repeated"] == 1
