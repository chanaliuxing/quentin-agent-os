import json
from pathlib import Path

from scripts.run_codex_timeout_canary import (
    _build_degraded_breakdown,
    _evaluate_promotion_gate,
    _load_run_observation,
)


def test_load_run_observation_reads_degraded_from_execution_summary(tmp_path: Path):
    workflow_id = "wf-001"
    phase_dir = tmp_path / "runtime" / "evidence" / workflow_id / "phase_01"
    phase_dir.mkdir(parents=True, exist_ok=True)
    (phase_dir / "execution_summary.json").write_text(
        json.dumps(
            {
                "terminal_state": "REJECTED",
                "primary_failure_type": "MISSING_REQUIRED_TEST",
                "runner_health_degraded_run": True,
                "runner_health_signals": ["AGENT_RUNNER_SESSION_DEGRADED"],
            }
        ),
        encoding="utf-8",
    )

    observation = _load_run_observation(root=tmp_path, workflow_id=workflow_id, timed_out=False)

    assert observation["terminal_state"] == "REJECTED"
    assert observation["primary_failure_type"] == "MISSING_REQUIRED_TEST"
    assert observation["degraded_run"] is True
    assert observation["runner_health_signals"] == ["AGENT_RUNNER_SESSION_DEGRADED"]


def test_load_run_observation_reads_degraded_from_delta_sidecar_when_summary_missing(tmp_path: Path):
    workflow_id = "wf-002"
    phase_dir = tmp_path / "runtime" / "evidence" / workflow_id / "phase_01"
    phase_dir.mkdir(parents=True, exist_ok=True)
    (phase_dir / "runner_health_delta.json").write_text(
        json.dumps(
            {
                "runner_health_degraded_run": True,
                "runner_health_signals": ["STATE_DB_DEGRADED", "RUNNER_USAGE_LIMIT"],
            }
        ),
        encoding="utf-8",
    )

    observation = _load_run_observation(root=tmp_path, workflow_id=workflow_id, timed_out=True)

    assert observation["terminal_state"] == "TIMEOUT"
    assert observation["primary_failure_type"] == "GLOBAL_TIMEOUT"
    assert observation["degraded_run"] is True
    assert observation["runner_health_signals"] == ["STATE_DB_DEGRADED", "RUNNER_USAGE_LIMIT"]


def test_evaluate_promotion_gate_rejects_on_degraded_rate():
    gate = _evaluate_promotion_gate(
        global_timeout_rate=0.0,
        reliability_degraded_run_rate=1.0,
        max_global_timeout_rate=0.0,
        max_degraded_run_rate=0.0,
    )
    assert gate["promotion_eligible"] is False
    assert "DEGRADED_RUN_RATE_EXCEEDED" in gate["gate_reasons"]


def test_evaluate_promotion_gate_accepts_when_below_thresholds():
    gate = _evaluate_promotion_gate(
        global_timeout_rate=0.0,
        reliability_degraded_run_rate=0.0,
        max_global_timeout_rate=0.0,
        max_degraded_run_rate=0.0,
    )
    assert gate["promotion_eligible"] is True
    assert gate["gate_reasons"] == []


def test_build_degraded_breakdown_produces_signal_rates_and_priority():
    breakdown = _build_degraded_breakdown(
        run_results=[
            {"runner_health_signals": ["AGENT_RUNNER_SESSION_DEGRADED", "STATE_DB_DEGRADED"]},
            {"runner_health_signals": ["AGENT_RUNNER_SESSION_DEGRADED"]},
            {"runner_health_signals": []},
        ],
        runs=3,
    )
    assert breakdown["session_degraded_run_rate"] == 2 / 3
    assert breakdown["state_db_degraded_run_rate"] == 1 / 3
    assert breakdown["reliability_degraded_run_rate"] == 2 / 3
    assert breakdown["top_priority_signal"] == "AGENT_RUNNER_SESSION_DEGRADED"


def test_build_degraded_breakdown_treats_usage_limit_as_capacity_signal():
    breakdown = _build_degraded_breakdown(
        run_results=[
            {"runner_health_signals": ["RUNNER_USAGE_LIMIT"]},
            {"runner_health_signals": []},
        ],
        runs=2,
    )
    assert breakdown["capacity_limited_run_rate"] == 0.5
    assert breakdown["reliability_degraded_run_rate"] == 0.0
