from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from verify_system import _audit_execution_process, _audit_intelligence_process, _load_calibrated_thresholds


def test_verify_system_process_audit_flags_missing_discovery_and_verification() -> None:
    result = SimpleNamespace(
        actions_summary="fs.write_file: extensions/tools/xh_leads/logic.py",
        final_output="done",
        self_awareness={},
    )
    issues = _audit_execution_process(result)
    assert "mutation_without_discovery_evidence" in issues
    assert "mutation_without_verification_evidence" in issues


def test_verify_system_process_audit_flags_antipattern_and_no_progress() -> None:
    result = SimpleNamespace(
        actions_summary="ls .",
        final_output="repeated_tool_call_loop",
        self_awareness={"anti_pattern_reason": "repeated_tool_call_loop", "consecutive_no_progress": 2},
    )
    issues = _audit_execution_process(result)
    assert "anti_pattern:repeated_tool_call_loop" in issues
    assert "repeated_tool_call_loop_detected" in issues
    assert "no_progress_streak>=2" in issues


def test_verify_system_intelligence_audit_flags_low_strategy_switch_effectiveness(tmp_path: Path, monkeypatch) -> None:
    events = tmp_path / "data" / "traces" / "events.jsonl"
    audits = tmp_path / "data" / "audit_events.jsonl"
    events.parent.mkdir(parents=True, exist_ok=True)
    audits.parent.mkdir(parents=True, exist_ok=True)
    with events.open("w", encoding="utf-8") as f:
        f.write(
            json.dumps(
                {
                    "trace_id": "t1",
                    "event_type": "planning",
                    "payload": {
                        "discovery_guard": {"risky_steps": 1, "discovery_before_risky": True},
                        "context_injected": {
                            "planning_diagnostics": {
                                "payload_variant_id": "",
                                "error_subcategory": "shell_permission_denied",
                                "strategy_patch_id": "",
                                "retry_delta_reason": "",
                            }
                        },
                    },
                },
                ensure_ascii=False,
            )
            + "\n"
        )
    monkeypatch.setenv("QUENTIN_VERIFY_STRATEGY_SWITCH_MIN", "0.6")
    issues = _audit_intelligence_process(repo_root=tmp_path)
    assert any("strategy_switch_effectiveness_below_threshold" in i for i in issues)


def test_verify_system_intelligence_audit_flags_low_execution_resilience(tmp_path: Path, monkeypatch) -> None:
    events = tmp_path / "data" / "traces" / "events.jsonl"
    audits = tmp_path / "data" / "audit_events.jsonl"
    events.parent.mkdir(parents=True, exist_ok=True)
    audits.parent.mkdir(parents=True, exist_ok=True)
    rows = [
        {
            "trace_id": "t1",
            "event_type": "critic",
            "payload": {"attempt_interrupt_state": "interrupt"},
        },
        {
            "trace_id": "t2",
            "event_type": "planning",
            "payload": {
                "planner_repairs": [],
                "context_injected": {"planning_diagnostics": {"force_progress_sync": True}},
            },
        },
    ]
    with events.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    monkeypatch.setenv("QUENTIN_VERIFY_INTERRUPT_EFFECTIVENESS_MIN", "0.8")
    monkeypatch.setenv("QUENTIN_VERIFY_PROGRESS_SYNC_COMPLIANCE_MIN", "0.9")
    issues = _audit_intelligence_process(repo_root=tmp_path)
    assert any("interrupt_effectiveness_below_threshold" in i for i in issues)
    assert any("progress_sync_compliance_below_threshold" in i for i in issues)


def test_verify_system_intelligence_audit_flags_low_attempt_band_coverage(tmp_path: Path, monkeypatch) -> None:
    events = tmp_path / "data" / "traces" / "events.jsonl"
    audits = tmp_path / "data" / "audit_events.jsonl"
    events.parent.mkdir(parents=True, exist_ok=True)
    audits.parent.mkdir(parents=True, exist_ok=True)
    with events.open("w", encoding="utf-8") as f:
        f.write(
            json.dumps(
                {
                    "trace_id": "t1",
                    "event_type": "planning",
                    "payload": {
                        "attempt_index": 4,
                        "discovery_guard": {"risky_steps": 1, "discovery_before_risky": True},
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
                ensure_ascii=False,
            )
            + "\n"
        )
    monkeypatch.setenv("QUENTIN_VERIFY_ATTEMPT_BAND_COVERAGE_MIN", "0.9")
    issues = _audit_intelligence_process(repo_root=tmp_path)
    assert any("attempt_band_coverage_below_threshold" in i for i in issues)


def test_verify_system_intelligence_audit_passes_when_effective(tmp_path: Path, monkeypatch) -> None:
    events = tmp_path / "data" / "traces" / "events.jsonl"
    audits = tmp_path / "data" / "audit_events.jsonl"
    events.parent.mkdir(parents=True, exist_ok=True)
    audits.parent.mkdir(parents=True, exist_ok=True)
    with events.open("w", encoding="utf-8") as f:
        f.write(
            json.dumps(
                {
                    "trace_id": "t1",
                    "event_type": "planning",
                    "payload": {
                        "discovery_guard": {"risky_steps": 1, "discovery_before_risky": True},
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
                ensure_ascii=False,
            )
            + "\n"
        )
    monkeypatch.setenv("QUENTIN_VERIFY_STRATEGY_SWITCH_MIN", "0.5")
    issues = _audit_intelligence_process(repo_root=tmp_path)
    assert issues == []


def test_load_calibrated_thresholds_from_history(tmp_path: Path, monkeypatch) -> None:
    hist = tmp_path / "planning_history.jsonl"
    rows = []
    for _ in range(10):
        rows.append(
            {
                "score_components": {
                    "strategy_switch_effectiveness": 0.52,
                    "interrupt_effectiveness": 0.65,
                    "reset_recovery_rate": 0.55,
                    "progress_sync_compliance": 0.88,
                },
                "intelligence_audit": {
                    "strategy_regression": {
                        "strategy_switching": {"attempt_band_coverage": 0.83}
                    }
                },
            }
        )
    hist.parent.mkdir(parents=True, exist_ok=True)
    with hist.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    monkeypatch.setenv("QUENTIN_VERIFY_AUTOCALIBRATE_FROM_HISTORY", "1")
    monkeypatch.setenv("QUENTIN_VERIFY_AUTOCALIBRATE_HISTORY_PATH", str(hist))
    monkeypatch.setenv("QUENTIN_VERIFY_AUTOCALIBRATE_MIN_SAMPLES", "8")
    out = _load_calibrated_thresholds()
    assert float(out.get("strategy_switch_effectiveness") or 0.0) > 0.40
    assert float(out.get("attempt_band_coverage") or 0.0) > 0.60


def test_verify_system_intelligence_audit_uses_calibrated_thresholds(tmp_path: Path, monkeypatch) -> None:
    events = tmp_path / "data" / "traces" / "events.jsonl"
    audits = tmp_path / "data" / "audit_events.jsonl"
    hist = tmp_path / "bench_history.jsonl"
    events.parent.mkdir(parents=True, exist_ok=True)
    audits.parent.mkdir(parents=True, exist_ok=True)
    with events.open("w", encoding="utf-8") as f:
        f.write(
            json.dumps(
                {
                    "trace_id": "t1",
                    "event_type": "planning",
                    "payload": {
                        "attempt_index": 4,
                        "discovery_guard": {"risky_steps": 1, "discovery_before_risky": True},
                        "context_injected": {
                            "planning_diagnostics": {
                                "attempt_band": "mid",
                                "payload_variant_id": "pv_retry_shell_tool_execution_error_shell_permission_denied_v1",
                                "error_subcategory": "shell_permission_denied",
                                "strategy_patch_id": "tool_guardrails_v1",
                                "retry_delta_reason": "retry_after=tool_execution_error",
                            }
                        },
                    },
                },
                ensure_ascii=False,
            )
            + "\n"
        )
    # Build history that calibrates threshold below 0.50.
    with hist.open("w", encoding="utf-8") as f:
        for _ in range(10):
            row = {
                "score_components": {
                    "strategy_switch_effectiveness": 0.48,
                    "interrupt_effectiveness": 0.60,
                    "reset_recovery_rate": 0.50,
                    "progress_sync_compliance": 0.85,
                },
                "intelligence_audit": {
                    "strategy_regression": {
                        "strategy_switching": {"attempt_band_coverage": 0.80}
                    }
                },
            }
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    monkeypatch.setenv("QUENTIN_VERIFY_AUTOCALIBRATE_FROM_HISTORY", "1")
    monkeypatch.setenv("QUENTIN_VERIFY_AUTOCALIBRATE_HISTORY_PATH", str(hist))
    monkeypatch.setenv("QUENTIN_VERIFY_AUTOCALIBRATE_MIN_SAMPLES", "8")
    monkeypatch.setenv("QUENTIN_VERIFY_STRATEGY_SWITCH_MIN", "0.70")
    issues = _audit_intelligence_process(repo_root=tmp_path)
    assert not any("strategy_switch_effectiveness_below_threshold" in i for i in issues)


def test_load_calibrated_thresholds_prefers_domain_bucket(tmp_path: Path, monkeypatch) -> None:
    hist = tmp_path / "bench_history.jsonl"
    hist.parent.mkdir(parents=True, exist_ok=True)
    with hist.open("w", encoding="utf-8") as f:
        # global strong values
        for _ in range(10):
            f.write(
                json.dumps(
                    {
                        "calibration_bucket": {"domain": "global"},
                        "score_components": {
                            "strategy_switch_effectiveness": 0.90,
                            "interrupt_effectiveness": 0.90,
                            "reset_recovery_rate": 0.90,
                            "progress_sync_compliance": 0.90,
                        },
                        "intelligence_audit": {"strategy_regression": {"strategy_switching": {"attempt_band_coverage": 0.90}}},
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )
        # maintenance weaker values
        for _ in range(10):
            f.write(
                json.dumps(
                    {
                        "calibration_bucket": {"domain": "maintenance"},
                        "score_components": {
                            "strategy_switch_effectiveness": 0.50,
                            "interrupt_effectiveness": 0.55,
                            "reset_recovery_rate": 0.52,
                            "progress_sync_compliance": 0.70,
                        },
                        "intelligence_audit": {"strategy_regression": {"strategy_switching": {"attempt_band_coverage": 0.75}}},
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )
    monkeypatch.setenv("QUENTIN_VERIFY_AUTOCALIBRATE_FROM_HISTORY", "1")
    monkeypatch.setenv("QUENTIN_VERIFY_AUTOCALIBRATE_HISTORY_PATH", str(hist))
    monkeypatch.setenv("QUENTIN_VERIFY_AUTOCALIBRATE_MIN_SAMPLES", "8")
    monkeypatch.setenv("QUENTIN_VERIFY_AUTOCALIBRATE_DOMAIN_BUCKET", "maintenance")
    out = _load_calibrated_thresholds()
    # Should follow maintenance bucket, not global bucket.
    assert float(out.get("strategy_switch_effectiveness") or 0.0) < 0.80


def test_load_calibrated_thresholds_falls_back_global_when_bucket_insufficient(tmp_path: Path, monkeypatch) -> None:
    hist = tmp_path / "bench_history.jsonl"
    hist.parent.mkdir(parents=True, exist_ok=True)
    with hist.open("w", encoding="utf-8") as f:
        for _ in range(10):
            f.write(
                json.dumps(
                    {
                        "calibration_bucket": {"domain": "global"},
                        "score_components": {
                            "strategy_switch_effectiveness": 0.62,
                            "interrupt_effectiveness": 0.66,
                            "reset_recovery_rate": 0.58,
                            "progress_sync_compliance": 0.80,
                        },
                        "intelligence_audit": {"strategy_regression": {"strategy_switching": {"attempt_band_coverage": 0.82}}},
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )
        # only 2 rows for research -> below min samples
        for _ in range(2):
            f.write(
                json.dumps(
                    {
                        "calibration_bucket": {"domain": "research"},
                        "score_components": {
                            "strategy_switch_effectiveness": 0.40,
                            "interrupt_effectiveness": 0.45,
                            "reset_recovery_rate": 0.40,
                            "progress_sync_compliance": 0.60,
                        },
                        "intelligence_audit": {"strategy_regression": {"strategy_switching": {"attempt_band_coverage": 0.70}}},
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )
    monkeypatch.setenv("QUENTIN_VERIFY_AUTOCALIBRATE_FROM_HISTORY", "1")
    monkeypatch.setenv("QUENTIN_VERIFY_AUTOCALIBRATE_HISTORY_PATH", str(hist))
    monkeypatch.setenv("QUENTIN_VERIFY_AUTOCALIBRATE_MIN_SAMPLES", "8")
    monkeypatch.setenv("QUENTIN_VERIFY_AUTOCALIBRATE_DOMAIN_BUCKET", "research")
    out = _load_calibrated_thresholds()
    # Should fallback to global bucket values.
    assert float(out.get("strategy_switch_effectiveness") or 0.0) > 0.50
