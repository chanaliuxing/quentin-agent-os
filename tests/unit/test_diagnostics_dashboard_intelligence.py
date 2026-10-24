from __future__ import annotations

from quentin.diagnostics.dashboard import (
    build_dashboard_snapshot,
    IntelligenceAlertThresholds,
)


def test_dashboard_snapshot_includes_intelligence_summary() -> None:
    snapshot = build_dashboard_snapshot(
        blueprint_report=None,
        immune_result=None,
        patch_reports=[],
        intelligence_report={
            "planner_repairs": {
                "repair_rate": 0.2,
                "repair_reason_counts": {"inject_discovery_precheck": 3},
                "discovery_precheck": {"compliance_rate": 0.95},
            },
            "blocked_action_recurrence": {"repeat_ratio": 0.1, "top_actions": [{"action": "nano", "count": 2}]},
            "done_council_quality": {"weak_resolution_rate": 0.9},
            "recovery_loop": {
                "success_rate": 0.9,
                "sample_size": 5,
                "recent_window_rate": 1.0,
                "prior_window_rate": 0.8,
                "trend_delta": 0.2,
                "trend_window_size": 2,
                "focus_breakdown": [{"focus": "guessing_trap", "total": 2, "done": 2, "failed": 0, "success_rate": 1.0}],
            },
        },
    )
    d = snapshot.to_dict()
    assert d["intelligence_summary"]["planner_repair_rate"] == 0.2
    assert d["intelligence_summary"]["discovery_precheck_compliance_rate"] == 0.95
    assert d["intelligence_summary"]["blocked_repeat_ratio"] == 0.1
    assert d["intelligence_summary"]["done_weak_resolution_rate"] == 0.9
    assert d["intelligence_summary"]["intelligence_recovery_success_rate"] == 0.9
    assert d["intelligence_summary"]["intelligence_recovery_sample_size"] == 5
    assert d["intelligence_summary"]["intelligence_recovery_trend_delta"] == 0.2
    assert d["intelligence_summary"]["intelligence_recovery_focus_breakdown"][0]["focus"] == "guessing_trap"
    assert d["intelligence_summary"]["planner_repair_reasons"]["inject_discovery_precheck"] == 3
    assert d["alerts"] == []


def test_dashboard_snapshot_triggers_intelligence_alerts() -> None:
    snapshot = build_dashboard_snapshot(
        blueprint_report=None,
        immune_result=None,
        patch_reports=[],
        intelligence_report={
            "planner_repairs": {
                "repair_rate": 0.8,
                "repair_reason_counts": {},
                "discovery_precheck": {"compliance_rate": 0.2},
            },
            "blocked_action_recurrence": {"repeat_ratio": 0.6, "top_actions": [{"action": "nano", "count": 5}]},
            "done_council_quality": {"weak_resolution_rate": 0.2},
            "recovery_loop": {
                "success_rate": 0.25,
                "sample_size": 8,
                "recent_window_rate": 0.0,
                "prior_window_rate": 0.75,
                "trend_delta": -0.75,
                "trend_window_size": 4,
                "focus_breakdown": [
                    {"focus": "guessing_trap", "total": 4, "done": 1, "failed": 3, "success_rate": 0.25},
                    {"focus": "semantic_stagnation", "total": 3, "done": 2, "failed": 1, "success_rate": 0.67},
                ],
            },
        },
        thresholds=IntelligenceAlertThresholds(
            planner_repair_rate_warn=0.3,
            blocked_repeat_ratio_warn=0.2,
            done_weak_resolution_rate_warn=0.5,
            discovery_precheck_compliance_warn=0.8,
            intelligence_recovery_success_rate_warn=0.6,
            intelligence_recovery_min_samples_warn=4,
            intelligence_recovery_trend_drop_warn=0.2,
            intelligence_recovery_focus_success_rate_warn=0.5,
            intelligence_recovery_focus_min_samples_warn=3,
        ),
    )
    codes = {a.get("code") for a in snapshot.alerts}
    assert "planner_repair_rate_high" in codes
    assert "blocked_action_repeat_high" in codes
    assert "done_weak_resolution_low" in codes
    assert "discovery_precheck_compliance_low" in codes
    assert "intelligence_recovery_success_low" in codes
    assert "intelligence_recovery_trend_down" in codes
    assert "intelligence_recovery_focus_low" in codes


def test_dashboard_snapshot_includes_audit_summary_and_alerts() -> None:
    snapshot = build_dashboard_snapshot(
        blueprint_report=None,
        immune_result=None,
        patch_reports=[],
        intelligence_report={},
        intelligence_audit_report={
            "guessing_trap": {"risky_without_discovery": 2, "discovery_compliance_rate": 0.4},
            "semantic_stagnation": {"weak_reasoning_detected": 3, "weak_resolution_rate": 0.33},
            "strategy_regression": {"fallback_decompositions": 2},
            "self_awareness_gap": {
                "blocked_action_repeated": 2,
                "top_repeated_actions": [{"action": "nano", "count": 2}],
            },
        },
        thresholds=IntelligenceAlertThresholds(
            blocked_action_repeated_warn=1,
            strategy_fallback_decompositions_warn=1,
        ),
    )
    d = snapshot.to_dict()
    assert d["intelligence_audit_summary"]["guessing_risky_without_discovery"] == 2
    assert d["intelligence_audit_summary"]["strategy_fallback_decompositions"] == 2
    assert d["intelligence_audit_summary"]["self_awareness_blocked_action_repeated"] == 2
    codes = {a.get("code") for a in snapshot.alerts}
    assert "guessing_trap_detected" in codes
    assert "strategy_regression_detected" in codes
    assert "blocked_action_repeated_detected" in codes
