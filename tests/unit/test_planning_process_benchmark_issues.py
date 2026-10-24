from __future__ import annotations

from scripts.planning_process_benchmark import analyze_benchmark_issues


def test_analyze_benchmark_issues_flags_low_metrics(monkeypatch) -> None:
    monkeypatch.setenv("QUENTIN_BENCH_PLANNING_MIN_PLANNING_EVENTS", "0")
    monkeypatch.setenv("QUENTIN_BENCH_PLANNING_DISCOVERY_COMPLIANCE_MIN", "0.90")
    monkeypatch.setenv("QUENTIN_BENCH_PLANNING_DIAG_COVERAGE_MIN", "0.80")
    monkeypatch.setenv("QUENTIN_BENCH_PLANNING_SUBCATEGORY_ALIGNMENT_MIN", "0.80")
    monkeypatch.setenv("QUENTIN_BENCH_PLANNING_COOLDOWN_RECURRENCE_MAX", "0.20")
    monkeypatch.setenv("QUENTIN_BENCH_PLANNING_BLOCKED_ACTION_REPEATED_MAX", "0")
    monkeypatch.setenv("QUENTIN_VERIFY_STRATEGY_SWITCH_MIN", "0.70")
    monkeypatch.setenv("QUENTIN_VERIFY_INTERRUPT_EFFECTIVENESS_MIN", "0.80")
    monkeypatch.setenv("QUENTIN_VERIFY_RESET_RECOVERY_MIN", "0.70")
    monkeypatch.setenv("QUENTIN_VERIFY_PROGRESS_SYNC_COMPLIANCE_MIN", "0.90")
    monkeypatch.setenv("QUENTIN_VERIFY_ATTEMPT_BAND_COVERAGE_MIN", "0.90")

    audit = {
        "guessing_trap": {
            "planning_events": 100,
            "risky_plans": 10,
            "risky_without_discovery": 2,
            "discovery_compliance_rate": 0.80,
            "examples": [{"trace_id": "t_bad"}],
        },
        "strategy_regression": {
            "strategy_switching": {
                "planning_diag_total": 30,
                "risky_without_diag": 6,
                "subcategory_alignment_rate": 0.50,
                "attempt_band_required": 10,
                "attempt_band_present": 5,
                "attempt_band_coverage": 0.50,
                "strategy_switch_effectiveness": 0.40,
                "examples": [{"trace_id": "t_diag", "payload_variant_id": "pv_retry_shell_x", "error_subcategory": "shell_timeout"}],
            },
            "execution_resilience": {
                "interrupt_total": 10,
                "hard_reset_total": 5,
                "interrupt_effectiveness": 0.60,
                "reset_recovery_rate": 0.40,
                "progress_sync_required": 10,
                "progress_sync_compliant": 6,
                "progress_sync_compliance": 0.60,
                "cooldown_events": 5,
                "cooldown_recurrence_rate": 0.40,
            },
        },
        "self_awareness_gap": {
            "blocked_action_repeated": 2,
            "top_repeated_actions": [{"action": "nano", "count": 2}],
        },
    }

    issues = analyze_benchmark_issues(audit)
    keys = {str(x.get("key") or "") for x in issues if isinstance(x, dict)}
    assert "discovery_before_risky_violation" in keys
    assert "discovery_compliance_below_threshold" in keys
    assert "planning_diagnostics_coverage_low" in keys
    assert "subcategory_alignment_low" in keys
    assert "strategy_switch_effectiveness_below_threshold" in keys
    assert "attempt_band_coverage_below_threshold" in keys
    assert "interrupt_effectiveness_below_threshold" in keys
    assert "reset_recovery_rate_below_threshold" in keys
    assert "progress_sync_compliance_below_threshold" in keys
    assert "cooldown_recurrence_high" in keys
    assert "blocked_action_recurrence" in keys


def test_analyze_benchmark_issues_passes_on_healthy_metrics(monkeypatch) -> None:
    monkeypatch.setenv("QUENTIN_BENCH_PLANNING_MIN_PLANNING_EVENTS", "0")
    monkeypatch.setenv("QUENTIN_BENCH_PLANNING_DISCOVERY_COMPLIANCE_MIN", "0.85")
    monkeypatch.setenv("QUENTIN_BENCH_PLANNING_DIAG_COVERAGE_MIN", "0.60")
    monkeypatch.setenv("QUENTIN_BENCH_PLANNING_SUBCATEGORY_ALIGNMENT_MIN", "0.65")
    monkeypatch.setenv("QUENTIN_BENCH_PLANNING_COOLDOWN_RECURRENCE_MAX", "0.35")
    monkeypatch.setenv("QUENTIN_BENCH_PLANNING_BLOCKED_ACTION_REPEATED_MAX", "0")
    monkeypatch.setenv("QUENTIN_VERIFY_STRATEGY_SWITCH_MIN", "0.55")
    monkeypatch.setenv("QUENTIN_VERIFY_INTERRUPT_EFFECTIVENESS_MIN", "0.50")
    monkeypatch.setenv("QUENTIN_VERIFY_RESET_RECOVERY_MIN", "0.40")
    monkeypatch.setenv("QUENTIN_VERIFY_PROGRESS_SYNC_COMPLIANCE_MIN", "0.80")
    monkeypatch.setenv("QUENTIN_VERIFY_ATTEMPT_BAND_COVERAGE_MIN", "0.80")
    monkeypatch.setenv("QUENTIN_BENCH_PLANNING_PLAN_EXEC_MIN_SAMPLES", "0")

    audit = {
        "guessing_trap": {
            "planning_events": 200,
            "risky_plans": 20,
            "risky_without_discovery": 0,
            "discovery_compliance_rate": 1.0,
        },
        "strategy_regression": {
            "strategy_switching": {
                "planning_diag_total": 200,
                "risky_without_diag": 0,
                "subcategory_alignment_rate": 0.95,
                "attempt_band_required": 10,
                "attempt_band_present": 10,
                "attempt_band_coverage": 1.0,
                "strategy_switch_effectiveness": 0.95,
                "plan_execution_consistency_total": 100,
                "plan_execution_consistency_rate": 1.0,
            },
            "execution_resilience": {
                "interrupt_total": 10,
                "hard_reset_total": 5,
                "interrupt_effectiveness": 1.0,
                "reset_recovery_rate": 0.9,
                "progress_sync_required": 10,
                "progress_sync_compliant": 10,
                "progress_sync_compliance": 1.0,
                "cooldown_events": 5,
                "cooldown_recurrence_rate": 0.0,
            },
        },
        "self_awareness_gap": {
            "blocked_action_repeated": 0,
        },
    }
    issues = analyze_benchmark_issues(audit)
    assert issues == []


def test_analyze_benchmark_issues_relaxes_strategy_threshold_for_legacy(monkeypatch) -> None:
    monkeypatch.setenv("QUENTIN_BENCH_PLANNING_MIN_PLANNING_EVENTS", "0")
    monkeypatch.setenv("QUENTIN_VERIFY_STRATEGY_SWITCH_MIN", "0.55")
    monkeypatch.setenv("QUENTIN_BENCH_PLANNING_STRATEGY_SWITCH_MIN_LEGACY", "0.25")
    monkeypatch.setenv("QUENTIN_VERIFY_INTERRUPT_EFFECTIVENESS_MIN", "0.50")
    monkeypatch.setenv("QUENTIN_VERIFY_RESET_RECOVERY_MIN", "0.40")
    monkeypatch.setenv("QUENTIN_VERIFY_PROGRESS_SYNC_COMPLIANCE_MIN", "0.80")
    monkeypatch.setenv("QUENTIN_VERIFY_ATTEMPT_BAND_COVERAGE_MIN", "0.80")
    monkeypatch.setenv("QUENTIN_BENCH_PLANNING_DISCOVERY_COMPLIANCE_MIN", "0.80")
    monkeypatch.setenv("QUENTIN_BENCH_PLANNING_DIAG_COVERAGE_MIN", "0.50")
    monkeypatch.setenv("QUENTIN_BENCH_PLANNING_SUBCATEGORY_ALIGNMENT_MIN", "0.50")
    monkeypatch.setenv("QUENTIN_BENCH_PLANNING_COOLDOWN_RECURRENCE_MAX", "0.80")
    monkeypatch.setenv("QUENTIN_BENCH_PLANNING_BLOCKED_ACTION_REPEATED_MAX", "5")

    audit = {
        "guessing_trap": {
            "planning_events": 20,
            "risky_plans": 10,
            "risky_without_discovery": 0,
            "discovery_compliance_rate": 1.0,
        },
        "strategy_regression": {
            "strategy_switching": {
                "planning_diag_total": 20,
                "legacy_diag_inferred": 20,
                "risky_without_diag": 0,
                "subcategory_alignment_rate": 1.0,
                "attempt_band_required": 8,
                "attempt_band_present": 8,
                "attempt_band_coverage": 1.0,
                "strategy_switch_effectiveness": 0.31,
            },
            "execution_resilience": {
                "interrupt_total": 10,
                "hard_reset_total": 5,
                "interrupt_effectiveness": 1.0,
                "reset_recovery_rate": 1.0,
                "progress_sync_required": 10,
                "progress_sync_compliant": 10,
                "progress_sync_compliance": 1.0,
                "cooldown_events": 5,
                "cooldown_recurrence_rate": 0.0,
            },
        },
        "self_awareness_gap": {
            "blocked_action_repeated": 0,
        },
    }
    issues = analyze_benchmark_issues(audit)
    keys = {str(x.get("key") or "") for x in issues if isinstance(x, dict)}
    assert "strategy_switch_effectiveness_below_threshold" not in keys


def test_analyze_benchmark_issues_flags_protocol_and_plan_exec(monkeypatch) -> None:
    monkeypatch.setenv("QUENTIN_BENCH_PLANNING_MIN_PLANNING_EVENTS", "0")
    monkeypatch.setenv("QUENTIN_BENCH_PLANNING_DISCOVERY_EVIDENCE_COVERAGE_MIN", "0.90")
    monkeypatch.setenv("QUENTIN_BENCH_PLANNING_PLAN_EXEC_CONSISTENCY_MIN", "0.80")
    monkeypatch.setenv("QUENTIN_BENCH_PLANNING_PLAN_EXEC_MIN_SAMPLES", "1")
    monkeypatch.setenv("QUENTIN_BENCH_PLANNING_PLAN_EXEC_EXACT_MATCH_MIN", "0.60")
    monkeypatch.setenv("QUENTIN_BENCH_PLANNING_PLAN_EXEC_EXACT_MIN_SAMPLES", "1")
    monkeypatch.setenv("QUENTIN_BENCH_PLANNING_MISALIGN_RECOVERY_MIN", "0.70")
    monkeypatch.setenv("QUENTIN_BENCH_PLANNING_MISALIGN_RECOVERY_MIN_SAMPLES", "1")
    monkeypatch.setenv("QUENTIN_BENCH_PLANNING_MISALIGN_RECURRENCE_MAX", "0.20")
    monkeypatch.setenv("QUENTIN_BENCH_PLANNING_PROTOCOL_FAILURE_MAX", "0.10")
    monkeypatch.setenv("QUENTIN_VERIFY_STRATEGY_SWITCH_MIN", "0.20")
    monkeypatch.setenv("QUENTIN_VERIFY_INTERRUPT_EFFECTIVENESS_MIN", "0.20")
    monkeypatch.setenv("QUENTIN_VERIFY_RESET_RECOVERY_MIN", "0.20")
    monkeypatch.setenv("QUENTIN_VERIFY_PROGRESS_SYNC_COMPLIANCE_MIN", "0.20")
    monkeypatch.setenv("QUENTIN_VERIFY_ATTEMPT_BAND_COVERAGE_MIN", "0.20")
    monkeypatch.setenv("QUENTIN_BENCH_PLANNING_DISCOVERY_COMPLIANCE_MIN", "0.20")
    monkeypatch.setenv("QUENTIN_BENCH_PLANNING_DIAG_COVERAGE_MIN", "0.20")
    monkeypatch.setenv("QUENTIN_BENCH_PLANNING_SUBCATEGORY_ALIGNMENT_MIN", "0.20")
    monkeypatch.setenv("QUENTIN_BENCH_PLANNING_COOLDOWN_RECURRENCE_MAX", "0.80")
    monkeypatch.setenv("QUENTIN_BENCH_PLANNING_BLOCKED_ACTION_REPEATED_MAX", "5")

    audit = {
        "perception_consistency": {
            "discovery_evidence_expected": 10,
            "discovery_evidence_found": 2,
            "discovery_evidence_coverage": 0.2,
            "examples_missing_evidence": [{"trace_id": "t1"}],
        },
        "guessing_trap": {
            "planning_events": 20,
            "risky_plans": 10,
            "risky_without_discovery": 0,
            "discovery_compliance_rate": 1.0,
        },
        "strategy_regression": {
            "strategy_switching": {
                "planning_diag_total": 20,
                "legacy_diag_inferred": 0,
                "risky_without_diag": 0,
                "subcategory_alignment_rate": 1.0,
                "attempt_band_required": 8,
                "attempt_band_present": 8,
                "attempt_band_coverage": 1.0,
                "strategy_switch_effectiveness": 1.0,
                "plan_execution_consistency_total": 10,
                "plan_execution_consistency_rate": 0.3,
                "plan_execution_exact_match_total": 10,
                "plan_execution_exact_match_rate": 0.1,
                "misalignment_eval_total": 10,
                "misalignment_recovered_within_2_rate": 0.2,
                "misalignment_recurrence_rate": 0.8,
                "plan_execution_consistency_examples": [{"trace_id": "tx"}],
            },
            "execution_resilience": {
                "interrupt_total": 10,
                "hard_reset_total": 5,
                "interrupt_effectiveness": 1.0,
                "reset_recovery_rate": 1.0,
                "progress_sync_required": 10,
                "progress_sync_compliant": 10,
                "progress_sync_compliance": 1.0,
                "cooldown_events": 5,
                "cooldown_recurrence_rate": 0.0,
            },
        },
        "protocol_fragility": {
            "protocol_turns": 10,
            "parse_failures": 4,
            "format_salvaged": 1,
            "protocol_fallbacks": 2,
            "protocol_failure_rate": 0.4,
        },
        "self_awareness_gap": {"blocked_action_repeated": 0},
    }
    issues = analyze_benchmark_issues(audit)
    keys = {str(x.get("key") or "") for x in issues if isinstance(x, dict)}
    assert "discovery_evidence_coverage_low" in keys
    assert "plan_execution_consistency_low" in keys
    assert "plan_execution_exact_alignment_low" in keys
    assert "misalignment_recovery_slow" in keys
    assert "misalignment_recurrence_high" in keys
    assert "protocol_failure_rate_high" in keys


def test_analyze_benchmark_issues_flags_missing_alignment_trace(monkeypatch) -> None:
    monkeypatch.setenv("QUENTIN_BENCH_PLANNING_MIN_PLANNING_EVENTS", "0")
    monkeypatch.setenv("QUENTIN_BENCH_PLANNING_ALIGNMENT_TRACE_MIN_EVENTS", "2")
    monkeypatch.setenv("QUENTIN_BENCH_PLANNING_ALIGNMENT_TRACE_MIN_PLANNING_EVENTS", "10")
    monkeypatch.setenv("QUENTIN_VERIFY_STRATEGY_SWITCH_MIN", "0.20")
    monkeypatch.setenv("QUENTIN_VERIFY_INTERRUPT_EFFECTIVENESS_MIN", "0.20")
    monkeypatch.setenv("QUENTIN_VERIFY_RESET_RECOVERY_MIN", "0.20")
    monkeypatch.setenv("QUENTIN_VERIFY_PROGRESS_SYNC_COMPLIANCE_MIN", "0.20")
    monkeypatch.setenv("QUENTIN_VERIFY_ATTEMPT_BAND_COVERAGE_MIN", "0.20")
    monkeypatch.setenv("QUENTIN_BENCH_PLANNING_DISCOVERY_COMPLIANCE_MIN", "0.20")
    monkeypatch.setenv("QUENTIN_BENCH_PLANNING_DIAG_COVERAGE_MIN", "0.20")
    monkeypatch.setenv("QUENTIN_BENCH_PLANNING_SUBCATEGORY_ALIGNMENT_MIN", "0.20")
    monkeypatch.setenv("QUENTIN_BENCH_PLANNING_COOLDOWN_RECURRENCE_MAX", "0.80")
    monkeypatch.setenv("QUENTIN_BENCH_PLANNING_BLOCKED_ACTION_REPEATED_MAX", "5")

    audit = {
        "guessing_trap": {
            "planning_events": 20,
            "risky_plans": 1,
            "risky_without_discovery": 0,
            "discovery_compliance_rate": 1.0,
        },
        "strategy_regression": {
            "strategy_switching": {
                "planning_diag_total": 20,
                "subcategory_alignment_rate": 1.0,
                "attempt_band_coverage": 1.0,
                "strategy_switch_effectiveness": 1.0,
                "plan_execution_consistency_total": 20,
                "plan_execution_consistency_rate": 1.0,
                "plan_execution_exact_match_total": 20,
                "plan_execution_exact_match_rate": 1.0,
                "plan_tool_alignment_trace_events": 0,
                "plan_tool_alignment_trace_blocked": 0,
                "plan_tool_alignment_trace_rewrites": 0,
            },
            "execution_resilience": {
                "interrupt_effectiveness": 1.0,
                "reset_recovery_rate": 1.0,
                "progress_sync_compliance": 1.0,
                "cooldown_recurrence_rate": 0.0,
            },
        },
        "self_awareness_gap": {"blocked_action_repeated": 0},
    }
    issues = analyze_benchmark_issues(audit)
    keys = {str(x.get("key") or "") for x in issues if isinstance(x, dict)}
    assert "plan_tool_alignment_trace_missing" in keys


def test_analyze_benchmark_issues_flags_low_execution_observed_coverage(monkeypatch) -> None:
    monkeypatch.setenv("QUENTIN_BENCH_PLANNING_MIN_PLANNING_EVENTS", "0")
    monkeypatch.setenv("QUENTIN_BENCH_PLANNING_EXEC_OBSERVED_COVERAGE_MIN", "0.80")
    monkeypatch.setenv("QUENTIN_BENCH_PLANNING_EXEC_OBSERVED_MIN_SAMPLES", "5")
    monkeypatch.setenv("QUENTIN_VERIFY_STRATEGY_SWITCH_MIN", "0.20")
    monkeypatch.setenv("QUENTIN_VERIFY_INTERRUPT_EFFECTIVENESS_MIN", "0.20")
    monkeypatch.setenv("QUENTIN_VERIFY_RESET_RECOVERY_MIN", "0.20")
    monkeypatch.setenv("QUENTIN_VERIFY_PROGRESS_SYNC_COMPLIANCE_MIN", "0.20")
    monkeypatch.setenv("QUENTIN_VERIFY_ATTEMPT_BAND_COVERAGE_MIN", "0.20")
    monkeypatch.setenv("QUENTIN_BENCH_PLANNING_DISCOVERY_COMPLIANCE_MIN", "0.20")
    monkeypatch.setenv("QUENTIN_BENCH_PLANNING_DIAG_COVERAGE_MIN", "0.20")
    monkeypatch.setenv("QUENTIN_BENCH_PLANNING_SUBCATEGORY_ALIGNMENT_MIN", "0.20")
    monkeypatch.setenv("QUENTIN_BENCH_PLANNING_COOLDOWN_RECURRENCE_MAX", "0.80")
    monkeypatch.setenv("QUENTIN_BENCH_PLANNING_BLOCKED_ACTION_REPEATED_MAX", "5")

    audit = {
        "guessing_trap": {
            "planning_events": 20,
            "risky_plans": 1,
            "risky_without_discovery": 0,
            "discovery_compliance_rate": 1.0,
        },
        "strategy_regression": {
            "strategy_switching": {
                "planning_diag_total": 20,
                "subcategory_alignment_rate": 1.0,
                "attempt_band_coverage": 1.0,
                "strategy_switch_effectiveness": 1.0,
                "plan_execution_consistency_total": 10,
                "plan_execution_consistency_rate": 1.0,
                "plan_execution_exact_match_total": 10,
                "plan_execution_exact_match_rate": 1.0,
                "plan_execution_expected_steps": 10,
                "plan_execution_observed_coverage": 0.2,
                "plan_execution_call_tool_coverage": 0.1,
            },
            "execution_resilience": {
                "interrupt_effectiveness": 1.0,
                "reset_recovery_rate": 1.0,
                "progress_sync_compliance": 1.0,
                "cooldown_recurrence_rate": 0.0,
            },
        },
        "self_awareness_gap": {"blocked_action_repeated": 0},
    }
    issues = analyze_benchmark_issues(audit)
    keys = {str(x.get("key") or "") for x in issues if isinstance(x, dict)}
    assert "plan_execution_observed_coverage_low" in keys


def test_analyze_benchmark_issues_flags_oscillation_and_protocol_semantics(monkeypatch) -> None:
    monkeypatch.setenv("QUENTIN_BENCH_PLANNING_MIN_PLANNING_EVENTS", "0")
    monkeypatch.setenv("QUENTIN_BENCH_PLANNING_GOAL_REANCHOR_MIN", "0.80")
    monkeypatch.setenv("QUENTIN_BENCH_PLANNING_OSCILLATION_MAX", "0")
    monkeypatch.setenv("QUENTIN_BENCH_PLANNING_PARSER_SEMANTIC_MIN", "0.90")
    monkeypatch.setenv("QUENTIN_BENCH_PLANNING_TRUNCATION_SALVAGE_MIN", "0.80")
    monkeypatch.setenv("QUENTIN_VERIFY_STRATEGY_SWITCH_MIN", "0.20")
    monkeypatch.setenv("QUENTIN_VERIFY_INTERRUPT_EFFECTIVENESS_MIN", "0.20")
    monkeypatch.setenv("QUENTIN_VERIFY_RESET_RECOVERY_MIN", "0.20")
    monkeypatch.setenv("QUENTIN_VERIFY_PROGRESS_SYNC_COMPLIANCE_MIN", "0.20")
    monkeypatch.setenv("QUENTIN_VERIFY_ATTEMPT_BAND_COVERAGE_MIN", "0.20")
    monkeypatch.setenv("QUENTIN_BENCH_PLANNING_DISCOVERY_COMPLIANCE_MIN", "0.20")
    monkeypatch.setenv("QUENTIN_BENCH_PLANNING_DIAG_COVERAGE_MIN", "0.20")
    monkeypatch.setenv("QUENTIN_BENCH_PLANNING_SUBCATEGORY_ALIGNMENT_MIN", "0.20")
    monkeypatch.setenv("QUENTIN_BENCH_PLANNING_COOLDOWN_RECURRENCE_MAX", "0.80")
    monkeypatch.setenv("QUENTIN_BENCH_PLANNING_BLOCKED_ACTION_REPEATED_MAX", "5")

    audit = {
        "guessing_trap": {"planning_events": 20, "risky_plans": 1, "risky_without_discovery": 0, "discovery_compliance_rate": 1.0},
        "strategy_regression": {
            "strategy_switching": {
                "planning_diag_total": 20,
                "subcategory_alignment_rate": 1.0,
                "attempt_band_coverage": 1.0,
                "strategy_switch_effectiveness": 1.0,
                "plan_execution_consistency_total": 20,
                "plan_execution_consistency_rate": 1.0,
                "plan_execution_exact_match_total": 20,
                "plan_execution_exact_match_rate": 1.0,
                "top_mismatch_patterns": [{"pattern": "fs.->shell.run_command", "count": 4}],
            },
            "execution_resilience": {
                "interrupt_effectiveness": 1.0,
                "reset_recovery_rate": 1.0,
                "progress_sync_compliance": 1.0,
                "cooldown_recurrence_rate": 0.0,
                "goal_reanchor_required": 3,
                "goal_reanchor_success": 1,
                "goal_reanchor_rate": 0.33,
                "plan_oscillation_events": 2,
            },
        },
        "protocol_fragility": {
            "protocol_turns": 10,
            "parse_failures": 0,
            "format_salvaged": 0,
            "protocol_fallbacks": 0,
            "protocol_failure_rate": 0.0,
            "parser_semantic_completeness": 0.2,
            "truncation_detected": 4,
            "truncation_salvaged": 1,
            "truncation_salvage_rate": 0.25,
        },
        "self_awareness_gap": {"blocked_action_repeated": 0},
    }
    issues = analyze_benchmark_issues(audit)
    keys = {str(x.get("key") or "") for x in issues if isinstance(x, dict)}
    assert "goal_reanchor_rate_low" in keys
    assert "plan_oscillation_high" in keys
    assert "parser_semantic_completeness_low" in keys
    assert "truncation_salvage_rate_low" in keys
    assert "top_mismatch_pattern_repeated" in keys
