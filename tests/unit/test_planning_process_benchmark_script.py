from __future__ import annotations

import json
from pathlib import Path

from scripts.planning_process_benchmark import compute_quality_score, run_benchmark


def test_compute_quality_score_uses_weighted_components() -> None:
    audit = {
        "strategy_regression": {
            "strategy_switching": {"strategy_switch_effectiveness": 0.5},
            "execution_resilience": {
                "interrupt_effectiveness": 1.0,
                "reset_recovery_rate": 0.5,
                "progress_sync_compliance": 1.0,
            },
        },
        "guessing_trap": {"discovery_compliance_rate": 1.0},
    }
    out = compute_quality_score(audit)
    score = float(out.get("quality_score") or 0.0)
    assert 0.0 <= score <= 1.0
    assert score > 0.6


def test_run_benchmark_writes_report_and_compares_previous(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("QUENTIN_BENCH_PLANNING_MIN_PLANNING_EVENTS", "2")
    monkeypatch.setenv("QUENTIN_BENCH_PLANNING_DISCOVERY_COMPLIANCE_MIN", "0.80")
    monkeypatch.setenv("QUENTIN_BENCH_PLANNING_DIAG_COVERAGE_MIN", "0.60")
    monkeypatch.setenv("QUENTIN_BENCH_PLANNING_SUBCATEGORY_ALIGNMENT_MIN", "0.60")
    monkeypatch.setenv("QUENTIN_VERIFY_STRATEGY_SWITCH_MIN", "0.55")
    monkeypatch.setenv("QUENTIN_VERIFY_INTERRUPT_EFFECTIVENESS_MIN", "0.50")
    monkeypatch.setenv("QUENTIN_VERIFY_RESET_RECOVERY_MIN", "0.40")
    monkeypatch.setenv("QUENTIN_VERIFY_PROGRESS_SYNC_COMPLIANCE_MIN", "0.80")
    monkeypatch.setenv("QUENTIN_VERIFY_ATTEMPT_BAND_COVERAGE_MIN", "0.80")

    events = tmp_path / "data" / "traces" / "events.jsonl"
    audits = tmp_path / "data" / "audit_events.jsonl"
    events.parent.mkdir(parents=True, exist_ok=True)
    audits.parent.mkdir(parents=True, exist_ok=True)
    rows = [
        {
            "trace_id": "t1",
            "event_type": "planning",
            "payload": {
                "planner_repairs": ["inject_progress_sync_step"],
                "discovery_guard": {"risky_steps": 1, "discovery_before_risky": True},
                "context_injected": {
                    "planning_diagnostics": {
                        "payload_variant_id": "pv_retry_shell_tool_execution_error_shell_permission_denied_v1",
                        "error_subcategory": "shell_permission_denied",
                        "strategy_patch_id": "tool_guardrails_v1",
                        "retry_delta_reason": "retry_after=tool_execution_error",
                        "force_progress_sync": True,
                    }
                },
            },
        },
        {"trace_id": "t1", "event_type": "critic", "payload": {"attempt_interrupt_state": "interrupt"}},
        {"trace_id": "t1", "event_type": "critic", "payload": {"done": True}},
    ]
    with events.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    previous = tmp_path / "generated" / "benchmarks" / "planning_prev.json"
    previous.parent.mkdir(parents=True, exist_ok=True)
    previous.write_text(json.dumps({"quality_score": 0.2}), encoding="utf-8")

    output = tmp_path / "generated" / "benchmarks" / "planning_report.json"
    history = tmp_path / "generated" / "benchmarks" / "planning_history.jsonl"
    report = run_benchmark(
        repo_root=tmp_path,
        output=output,
        previous=previous,
        min_score=0.3,
        history=history,
        domain_bucket="maintenance",
    )

    assert output.exists()
    assert history.exists()
    assert (report.get("calibration_bucket") or {}).get("domain") == "maintenance"
    assert float(report.get("quality_score") or 0.0) >= 0.3
    assert report.get("improved_vs_previous") is True
    assert 0.0 <= float(report.get("quality_score_v2") or 0.0) <= 1.0
    assert isinstance(report.get("dimension_scores"), dict)
    assert isinstance(report.get("capability_radar"), dict)
    radar = report.get("capability_radar") or {}
    for key in (
        "perception_consistency",
        "planning_consistency",
        "dynamic_correction",
        "protocol_robustness",
        "process_completeness",
    ):
        assert key in radar
    assert isinstance(report.get("top_weaknesses"), list)
    assert isinstance(report.get("issues"), list)
    assert isinstance(report.get("domain_breakdown"), dict)
    assert "maintenance" in (report.get("domain_breakdown") or {})
    switching_components = (
        ((report.get("dimension_scores") or {}).get("strategy_switching") or {}).get("components") or {}
    )
    assert "plan_execution_exact_match_total" in switching_components
    assert "plan_execution_exact_match_rate" in switching_components
    assert "plan_execution_expected_steps" in switching_components
    assert "plan_execution_observed_coverage" in switching_components
    assert "plan_execution_call_tool_coverage" in switching_components
    assert "plan_tool_alignment_trace_events" in switching_components
    assert "plan_tool_alignment_trace_blocked" in switching_components
    assert "plan_tool_alignment_trace_rewrites" in switching_components
    issue_keys = {str(x.get("key") or "") for x in (report.get("issues") or []) if isinstance(x, dict)}
    assert "insufficient_planning_samples" in issue_keys


def test_run_benchmark_adaptive_alias_ab_mode(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("QUENTIN_BENCH_ADAPTIVE_ALIAS_AB", "1")
    monkeypatch.setenv("QUENTIN_BENCH_PLANNING_MIN_PLANNING_EVENTS", "0")
    events = tmp_path / "data" / "traces" / "events.jsonl"
    events.parent.mkdir(parents=True, exist_ok=True)
    events.write_text(
        json.dumps(
            {
                "trace_id": "tab",
                "event_type": "execution",
                "payload": {
                    "raw": {
                        "steps": [
                            {
                                "step_id": "s1",
                                "description": "Use fs.read_file to inspect file.",
                                "result": {
                                    "status": "ok",
                                    "meta": {"protocol_chain": ["native_tools"]},
                                    "tool_result": {"tool_name": "cat"},
                                },
                            }
                        ]
                    }
                },
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    output = tmp_path / "generated" / "benchmarks" / "planning_report.json"
    report = run_benchmark(repo_root=tmp_path, output=output, previous=None, min_score=0.0, history=None, domain_bucket="research")
    ab = report.get("adaptive_alias_ab") or {}
    assert bool(ab.get("enabled"))
    assert "exact_match_rate_static" in ab
    assert "exact_match_rate_adaptive" in ab
