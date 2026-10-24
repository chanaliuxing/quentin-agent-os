from __future__ import annotations

import json
from pathlib import Path

from quentin.diagnostics.intelligence_auditor import build_intelligence_audit


def _append_jsonl(path: Path, row: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def test_build_intelligence_audit_extracts_four_symptoms(tmp_path) -> None:
    events = tmp_path / "data" / "traces" / "events.jsonl"
    audits = tmp_path / "data" / "audit_events.jsonl"

    _append_jsonl(
        events,
        {
            "trace_id": "t1",
            "event_type": "planning",
            "payload": {
                "planner_repairs": ["decompose_single_step_fallback"],
                "discovery_guard": {
                    "risky_steps": 1,
                    "discovery_before_risky": False,
                    "first_risky_step_id": "s2",
                    "first_discovery_step_id": "",
                },
                "context_injected": {
                    "planning_diagnostics": {
                        "payload_variant_id": "pv_retry_shell_tool_execution_error_shell_permission_denied_v1",
                        "error_subcategory": "shell_permission_denied",
                        "strategy_patch_id": "tool_guardrails_v1",
                        "retry_delta_reason": "retry_after=tool_execution_error",
                    }
                },
            },
        },
    )
    _append_jsonl(
        events,
        {
            "trace_id": "t2",
            "event_type": "planning",
            "payload": {
                "planner_repairs": ["prevent_strategy_regression_reused_previous_decomposition"],
                "discovery_guard": {
                    "risky_steps": 1,
                    "discovery_before_risky": True,
                    "first_risky_step_id": "s2",
                    "first_discovery_step_id": "s1",
                },
                "context_injected": {
                    "planning_diagnostics": {
                        "payload_variant_id": "pv_retry_browser_tool_execution_error_browser_selector_not_found_v1",
                        "error_subcategory": "browser_selector_not_found",
                        "strategy_patch_id": "tool_guardrails_v1",
                        "retry_delta_reason": "retry_after=tool_execution_error",
                    }
                },
            },
        },
    )

    _append_jsonl(audits, {"event_type": "done_council_quality", "phase": "weak_reasoning_detected", "payload": {}})
    _append_jsonl(audits, {"event_type": "done_council_quality", "phase": "retry_improved", "payload": {}})
    _append_jsonl(audits, {"event_type": "action_exec", "phase": "denied", "payload": {"command": "nano file.py"}})
    _append_jsonl(audits, {"event_type": "action_exec", "phase": "denied", "payload": {"command": "nano file.py"}})

    report = build_intelligence_audit(repo_root=tmp_path)

    assert report["guessing_trap"]["risky_plans"] == 2
    assert report["guessing_trap"]["risky_without_discovery"] == 1
    assert report["strategy_regression"]["fallback_decompositions"] == 1
    assert report["strategy_regression"]["repair_reused_previous_decomposition"] == 1
    switching = report["strategy_regression"]["strategy_switching"]
    assert switching["planning_diag_total"] == 2
    assert switching["variant_coverage"] == 1.0
    assert switching["strategy_patch_coverage"] == 1.0
    assert switching["retry_delta_coverage"] == 1.0
    assert switching["subcategory_alignment_rate"] == 1.0
    assert switching["plan_execution_consistency_rate"] == 1.0
    assert switching["plan_execution_expected_steps"] == 0
    assert switching["plan_execution_observed_coverage"] == 1.0
    assert switching["plan_execution_call_tool_coverage"] == 1.0
    assert report["semantic_stagnation"]["weak_reasoning_detected"] == 1
    assert report["semantic_stagnation"]["weak_reasoning_resolved"] == 1
    assert report["self_awareness_gap"]["blocked_action_repeated"] == 1
    perception = report["perception_consistency"]
    assert perception["discovery_evidence_expected"] == 2
    assert perception["discovery_evidence_found"] == 1
    assert perception["discovery_evidence_coverage"] == 0.5


def test_build_intelligence_audit_infers_legacy_planning_diagnostics(tmp_path) -> None:
    events = tmp_path / "data" / "traces" / "events.jsonl"
    audits = tmp_path / "data" / "audit_events.jsonl"

    _append_jsonl(
        events,
        {
            "trace_id": "t_legacy_1",
            "event_type": "planning",
            "payload": {
                "attempt_index": 3,
                "planner_repairs": [],
                "discovery_guard": {
                    "risky_steps": 1,
                    "discovery_before_risky": True,
                    "first_risky_step_id": "s2",
                    "first_discovery_step_id": "s1",
                },
                "raw_output": "{\"steps\":[{\"step_id\":\"s1\",\"notes\":\"antipattern_recovery:repeated_tool_call_loop\"}],\"metadata\":{\"source\":\"antipattern_recovery\",\"reason\":\"repeated_tool_call_loop\"}}",
                "context_injected": {"tree_lines": 100, "candidate_files_count": 5},
            },
        },
    )
    _append_jsonl(
        events,
        {
            "trace_id": "t_legacy_2",
            "event_type": "planning",
            "payload": {
                "attempt_index": 4,
                "planner_repairs": [],
                "discovery_guard": {
                    "risky_steps": 1,
                    "discovery_before_risky": True,
                    "first_risky_step_id": "s2",
                    "first_discovery_step_id": "s1",
                },
                "raw_output": "{\"steps\":[{\"step_id\":\"s1\",\"notes\":\"antipattern_recovery:repeated_tool_call_loop\"}],\"metadata\":{\"source\":\"antipattern_recovery\",\"reason\":\"repeated_tool_call_loop\"}}",
                "context_injected": {"tree_lines": 100, "candidate_files_count": 5},
            },
        },
    )
    _append_jsonl(audits, {"event_type": "done_council_quality", "phase": "weak_reasoning_detected", "payload": {}})

    report = build_intelligence_audit(repo_root=tmp_path)
    switching = report["strategy_regression"]["strategy_switching"]
    assert switching["planning_diag_total"] == 2
    assert switching["legacy_diag_inferred"] == 2
    assert switching["variant_coverage"] == 1.0
    assert switching["strategy_patch_coverage"] == 1.0
    assert switching["retry_delta_coverage"] == 1.0
    assert switching["attempt_band_coverage"] == 1.0


def test_build_intelligence_audit_extracts_protocol_fragility_and_plan_exec_mismatch(tmp_path) -> None:
    events = tmp_path / "data" / "traces" / "events.jsonl"
    audits = tmp_path / "data" / "audit_events.jsonl"
    _append_jsonl(
        events,
        {
            "trace_id": "t_exec",
            "event_type": "execution",
            "payload": {
                "raw": {
                    "steps": [
                        {
                            "step_id": "s1",
                            "description": "Use fs.read_file to inspect config.",
                            "result": {
                                "status": "error",
                                "error": "parse_failure",
                                "feedback_tail": [
                                    {"type": "tool_alignment_violation", "reason": "plan_execution_misalignment", "blocked": True},
                                    {"type": "tool_alignment_rewrite", "reason": "plan_execution_misalignment", "blocked": False},
                                ],
                                "meta": {
                                    "protocol_chain": ["native_tools", "json_mode"],
                                    "format_salvaged": True,
                                },
                                "tool_result": {"tool_name": "shell.run_command"},
                            },
                        }
                    ]
                }
            },
        },
    )
    _append_jsonl(
        events,
        {
            "trace_id": "t_exec",
            "event_type": "execution",
            "payload": {
                "signal": "plan_tool_alignment",
                "event_type": "tool_alignment_rewrite",
                "reason": "plan_execution_misalignment",
                "blocked": False,
            },
        },
    )
    _append_jsonl(
        events,
        {
            "trace_id": "t_exec",
            "event_type": "decision",
            "payload": {
                "signal": "plan_tool_alignment",
                "event_type": "tool_alignment_violation",
                "reason": "plan_execution_misalignment",
                "blocked": True,
            },
        },
    )
    _append_jsonl(
        events,
        {
            "trace_id": "t_plan",
            "event_type": "planning",
            "payload": {
                "attempt_index": 3,
                "discovery_guard": {
                    "risky_steps": 1,
                    "discovery_before_risky": True,
                    "first_risky_step_id": "s2",
                    "first_discovery_step_id": "",
                },
                "context_injected": {
                    "planning_diagnostics": {
                        "payload_variant_id": "pv_retry_shell_tool_execution_error_shell_permission_denied_v1",
                        "error_subcategory": "shell_permission_denied",
                        "strategy_patch_id": "tool_guardrails_v1",
                        "retry_delta_reason": "retry_after=tool_execution_error",
                        "attempt_band": "mid",
                    }
                },
            },
        },
    )
    _append_jsonl(
        events,
        {
            "trace_id": "t_exec",
            "event_type": "critic",
            "payload": {
                "action": "attempt_evaluated",
                "attempt_index": 1,
                "attempt_evaluation": {
                    "category": "plan_execution_misalignment",
                    "error_subcategory": "plan_execution_misalignment",
                },
            },
        },
    )
    _append_jsonl(
        events,
        {
            "trace_id": "t_exec",
            "event_type": "critic",
            "payload": {
                "action": "attempt_evaluated",
                "attempt_index": 2,
                "attempt_evaluation": {
                    "category": "success",
                    "error_subcategory": "",
                },
            },
        },
    )
    _append_jsonl(audits, {"event_type": "done_council_quality", "phase": "weak_reasoning_detected", "payload": {}})

    report = build_intelligence_audit(repo_root=tmp_path)
    protocol = report["protocol_fragility"]
    assert protocol["protocol_turns"] == 1
    assert protocol["parse_failures"] == 1
    assert protocol["format_salvaged"] == 1
    assert protocol["protocol_fallbacks"] == 1
    assert protocol["protocol_failure_rate"] == 1.0
    assert protocol["truncation_detected"] == 0
    assert protocol["truncation_salvage_rate"] == 1.0
    assert protocol["parser_semantic_completeness"] == 0.0
    switching = report["strategy_regression"]["strategy_switching"]
    assert switching["plan_execution_consistency_total"] == 1
    assert switching["plan_execution_consistency_rate"] == 0.0
    assert switching["plan_execution_exact_match_total"] == 1
    assert switching["plan_execution_exact_match_rate"] == 0.0
    assert switching["plan_execution_expected_steps"] == 1
    assert switching["plan_execution_observed_coverage"] == 1.0
    assert switching["adaptive_alias_entries"] >= 0
    assert switching["plan_tool_alignment_events"] == 2
    assert switching["plan_tool_alignment_blocked"] == 1
    assert switching["plan_tool_alignment_rewrites"] == 1
    assert switching["plan_tool_alignment_trace_events"] == 2
    assert switching["plan_tool_alignment_trace_blocked"] == 1
    assert switching["plan_tool_alignment_trace_rewrites"] == 1
    assert switching["misalignment_eval_total"] == 1
    assert switching["misalignment_recovered_within_2"] == 1
    assert switching["misalignment_recurred_within_2"] == 0
    assert switching["misalignment_recovered_within_2_rate"] == 1.0
    perception = report["perception_consistency"]
    assert perception["discovery_evidence_expected"] == 1
    assert perception["discovery_evidence_found"] == 0


def test_build_intelligence_audit_normalizes_legacy_tool_alias_for_plan_exec(tmp_path) -> None:
    events = tmp_path / "data" / "traces" / "events.jsonl"
    _append_jsonl(
        events,
        {
            "trace_id": "t_exec_alias",
            "event_type": "execution",
            "payload": {
                "raw": {
                    "steps": [
                        {
                            "step_id": "s1",
                            "description": "Use fs.list_dir to inspect project files.",
                            "result": {
                                "status": "ok",
                                "meta": {"protocol_chain": ["native_tools"]},
                                "tool_result": {"tool_name": "ls"},
                            },
                        }
                    ]
                }
            },
        },
    )

    report = build_intelligence_audit(repo_root=tmp_path)
    switching = report["strategy_regression"]["strategy_switching"]
    assert switching["plan_execution_consistency_total"] == 1
    assert switching["plan_execution_exact_match_total"] == 1
    # Exact alignment should also pass after canonical alias normalization.
    assert switching["plan_execution_exact_match_rate"] == 1.0
    assert switching["plan_execution_consistency_rate"] == 1.0


def test_build_intelligence_audit_replay_mixed_aliases_for_exact_alignment(tmp_path) -> None:
    events = tmp_path / "data" / "traces" / "events.jsonl"
    _append_jsonl(
        events,
        {
            "trace_id": "t_exec_mixed_aliases",
            "event_type": "execution",
            "payload": {
                "raw": {
                    "steps": [
                        {
                            "step_id": "s1",
                            "description": "Use fs.read_file to inspect AGENTS.md.",
                            "result": {"status": "ok", "meta": {"protocol_chain": ["native_tools"]}, "tool_result": {"tool_name": "cat"}},
                        },
                        {
                            "step_id": "s2",
                            "description": "Use browser.navigate to open the docs page.",
                            "result": {"status": "ok", "meta": {"protocol_chain": ["native_tools"]}, "tool_result": {"tool_name": "open_url"}},
                        },
                        {
                            "step_id": "s3",
                            "description": "Use shell.run_command to verify runtime state.",
                            "result": {"status": "ok", "meta": {"protocol_chain": ["native_tools"]}, "tool_result": {"tool_name": "bash"}},
                        },
                    ]
                }
            },
        },
    )

    report = build_intelligence_audit(repo_root=tmp_path)
    switching = report["strategy_regression"]["strategy_switching"]
    assert switching["plan_execution_consistency_total"] == 3
    assert switching["plan_execution_expected_steps"] == 3
    assert switching["plan_execution_observed_coverage"] == 1.0
    assert switching["plan_execution_call_tool_coverage"] == 0.0
    assert switching["plan_execution_exact_match_total"] == 3
    assert switching["plan_execution_exact_match_rate"] == 1.0
    assert switching["plan_execution_consistency_rate"] == 1.0


def test_build_intelligence_audit_goal_reanchor_and_oscillation_metrics(tmp_path) -> None:
    events = tmp_path / "data" / "traces" / "events.jsonl"
    # A long trajectory with two hard resets and repeated plan signature after reset.
    for idx in range(1, 13):
        _append_jsonl(
            events,
            {
                "trace_id": "t_long",
                "event_type": "planning",
                "payload": {
                    "attempt_index": idx,
                    "raw": {"steps": [{"description": "same-path-step" if idx in {4, 8} else f"step-{idx}"}]},
                },
            },
        )
        if idx in {3, 7}:
            _append_jsonl(
                events,
                {
                    "trace_id": "t_long",
                    "event_type": "critic",
                    "payload": {
                        "attempt_interrupt_state": "hard_reset",
                        "attempt_index": idx,
                    },
                },
            )
    _append_jsonl(events, {"trace_id": "t_long", "event_type": "critic", "payload": {"done": True}})

    report = build_intelligence_audit(repo_root=tmp_path)
    resilience = (report.get("strategy_regression") or {}).get("execution_resilience") or {}
    assert int(resilience.get("goal_reanchor_required") or 0) >= 1
    assert float(resilience.get("goal_reanchor_rate") or 0.0) >= 0.0
    assert int(resilience.get("plan_oscillation_events") or 0) >= 0


def test_build_intelligence_audit_truncation_and_malformed_payload_resilience(tmp_path) -> None:
    events = tmp_path / "data" / "traces" / "events.jsonl"
    _append_jsonl(
        events,
        {
            "trace_id": "t_proto",
            "event_type": "execution",
            "payload": {
                "raw": {
                    "steps": [
                        {
                            "step_id": "s1",
                            "description": "Use shell.run_command to run health check.",
                            "result": {
                                "status": "error",
                                "error": "unexpected EOF while parsing truncated response",
                                "meta": {
                                    "protocol_chain": ["json_mode", "native_tools"],
                                    "format_salvaged": True,
                                },
                                "tool_result": {"tool_name": "shell.run_command"},
                            },
                        },
                        {
                            "step_id": "s2",
                            "description": "Use fs.read_file to inspect output.",
                            "result": {
                                "status": "error",
                                "error": "json_parse_error: mixed <xml>{json",
                                "meta": {"protocol_chain": ["json_mode"], "format_salvaged": False},
                            },
                        },
                    ]
                }
            },
        },
    )

    report = build_intelligence_audit(repo_root=tmp_path)
    protocol = report["protocol_fragility"]
    assert protocol["protocol_turns"] == 2
    assert protocol["truncation_detected"] == 1
    assert protocol["truncation_salvaged"] == 1
    assert protocol["truncation_salvage_rate"] == 1.0
    assert 0.0 <= float(protocol["parser_semantic_completeness"]) <= 1.0


def test_build_intelligence_audit_adaptive_alias_ab_improves_exact_alignment(tmp_path, monkeypatch) -> None:
    events = tmp_path / "data" / "traces" / "events.jsonl"
    # Repeated family-consistent mismatch: expected fs.write_file, actual fs.mkdir.
    for idx in range(3):
        _append_jsonl(
            events,
            {
                "trace_id": "t_adapt",
                "event_type": "execution",
                "payload": {
                    "raw": {
                        "steps": [
                            {
                                "step_id": f"s{idx}",
                                "description": "Use fs.write_file to create marker file.",
                                "result": {
                                    "status": "ok",
                                    "meta": {"protocol_chain": ["json_mode"]},
                                    "tool_result": {"tool_name": "mkdir"},
                                },
                            }
                        ]
                    }
                },
            },
        )

    monkeypatch.setenv("QUENTIN_PLAN_EXEC_ADAPTIVE_ALIAS_MIN_SUPPORT", "2")
    static_report = build_intelligence_audit(repo_root=tmp_path, adaptive_alias=False)
    adaptive_report = build_intelligence_audit(repo_root=tmp_path, adaptive_alias=True)
    s0 = (static_report.get("strategy_regression") or {}).get("strategy_switching") or {}
    s1 = (adaptive_report.get("strategy_regression") or {}).get("strategy_switching") or {}
    assert float(s1.get("plan_execution_exact_match_rate") or 0.0) >= float(s0.get("plan_execution_exact_match_rate") or 0.0)
    assert int(s1.get("adaptive_alias_entries") or 0) >= 1


def test_build_intelligence_audit_adaptive_alias_guardrails_min_support(tmp_path, monkeypatch) -> None:
    events = tmp_path / "data" / "traces" / "events.jsonl"
    _append_jsonl(
        events,
        {
            "trace_id": "t_adapt_guard",
            "event_type": "execution",
            "payload": {
                "raw": {
                    "steps": [
                        {
                            "step_id": "s1",
                            "description": "Use fs.write_file to create marker file.",
                            "result": {
                                "status": "ok",
                                "meta": {"protocol_chain": ["json_mode"]},
                                "tool_result": {"tool_name": "mkdir"},
                            },
                        }
                    ]
                }
            },
        },
    )
    monkeypatch.setenv("QUENTIN_PLAN_EXEC_ADAPTIVE_ALIAS_MIN_SUPPORT", "3")
    report = build_intelligence_audit(repo_root=tmp_path, adaptive_alias=True)
    switching = (report.get("strategy_regression") or {}).get("strategy_switching") or {}
    assert int(switching.get("adaptive_alias_entries") or 0) == 0
