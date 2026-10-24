from __future__ import annotations

import json
from pathlib import Path

import pytest

from quentin.benchmarks.tool_adaptation import run_benchmark

pytestmark = [
    pytest.mark.filterwarnings("ignore:.*Pydantic V1 style `@root_validator`.*"),
    pytest.mark.filterwarnings("ignore:.*datetime.datetime.utcnow\\(\\) is deprecated.*"),
]


def _find_repo_root(start: Path) -> Path:
    p = start.resolve()
    for cand in [p, *p.parents]:
        if (cand / "pyproject.toml").exists() and (cand / "quentin").exists():
            return cand
    return p


def test_run_tool_adaptation_benchmark_writes_report_and_cases(tmp_path: Path) -> None:
    repo_root = _find_repo_root(Path(__file__))

    previous = tmp_path / "prev.json"
    previous.write_text(json.dumps({"quality_score": 0.1}), encoding="utf-8")

    output = tmp_path / "report.json"
    history = tmp_path / "history.jsonl"
    trend_ndjson = tmp_path / "trend.ndjson"
    report = run_benchmark(
        repo_root=repo_root,
        output=output,
        previous=previous,
        history=history,
        min_score=0.0,
        domain_bucket="tools",
        trend_ndjson_output=trend_ndjson,
    )

    assert output.exists()
    assert history.exists()
    assert trend_ndjson.exists()
    assert (report.get("calibration_bucket") or {}).get("domain") == "tools"
    assert report.get("schema_version") == "2.0.0"
    assert isinstance(report.get("schema_validation"), dict)
    assert bool((report.get("schema_validation") or {}).get("ok")) is True
    assert bool((report.get("schema_validation") or {}).get("schema_loaded")) is True
    assert isinstance(report.get("trend_guard"), dict)
    assert isinstance(report.get("timeout_summary"), dict)
    assert isinstance((report.get("timeout_summary") or {}).get("runtime_percentiles_ms"), dict)
    assert isinstance((report.get("timeout_summary") or {}).get("tool_runtime_percentiles_ms"), dict)
    assert isinstance(report.get("trend_export"), dict)
    assert isinstance(report.get("regression_explain"), dict)
    assert isinstance(report.get("remediation_queue"), list)
    assert isinstance(report.get("replay"), dict)
    assert isinstance(report.get("weight_tuning"), dict)
    assert isinstance(report.get("weights_base"), dict)
    assert 0.0 <= float(report.get("quality_score") or 0.0) <= 1.0
    assert report.get("improved_vs_previous") is True

    cases = report.get("cases") or []
    assert isinstance(cases, list)
    case_ids = {c.get("case_id") for c in cases if isinstance(c, dict)}
    assert "container_tool_plugins_visible" in case_ids
    assert "tool_usage_writeback_to_memory" in case_ids
    assert "exec_skill_plugin_discovery" in case_ids
    assert "decision_memory_reuse_effect" in case_ids
    assert "memory_conflict_resolution" in case_ids
    assert "full_loop_adversarial_memory" in case_ids
    assert "channel_gateway_contract" in case_ids
    assert "domain_adapter_channel_gateway" in case_ids
    assert "channel_provider_config_gate" in case_ids
    assert "channel_listener_resilience_policy" in case_ids
    assert "nl_generalization_affordance" in case_ids
    assert "failure_recovery_fallback" in case_ids
    assert "cross_session_persistence" in case_ids
    assert "meta_agent_registry_path" in case_ids

    # At least one core case should pass; otherwise the benchmark can't guide regressions.
    passed = [c for c in cases if isinstance(c, dict) and bool(c.get("passed"))]
    assert len(passed) >= 1
    row = json.loads(trend_ndjson.read_text(encoding="utf-8").strip().splitlines()[-1])
    assert isinstance(row, dict)
    assert "quality_score" in row


def test_run_tool_adaptation_benchmark_disable_auto_tune_keeps_mode(tmp_path: Path) -> None:
    repo_root = _find_repo_root(Path(__file__))
    output = tmp_path / "report.json"
    history = tmp_path / "history.jsonl"
    history.write_text(json.dumps({"quality_score": 0.5, "issues": []}, ensure_ascii=False) + "\n", encoding="utf-8")

    report = run_benchmark(
        repo_root=repo_root,
        output=output,
        history=history,
        min_score=0.0,
        auto_tune_weights=False,
    )

    tuning = report.get("weight_tuning") if isinstance(report.get("weight_tuning"), dict) else {}
    assert str(tuning.get("mode") or "") == "disabled"
    assert bool(tuning.get("enabled")) is False


def test_run_tool_adaptation_benchmark_trend_guard_can_fail(tmp_path: Path) -> None:
    repo_root = _find_repo_root(Path(__file__))
    output = tmp_path / "report.json"
    history = tmp_path / "history.jsonl"
    history.write_text(json.dumps({"quality_score": 1.2}, ensure_ascii=False) + "\n", encoding="utf-8")

    report = run_benchmark(
        repo_root=repo_root,
        output=output,
        history=history,
        min_score=0.0,
        moving_window=1,
        trend_drop_tolerance=0.0,
    )

    assert isinstance(report.get("trend_guard"), dict)
    assert bool((report.get("trend_guard") or {}).get("pass")) is False
    assert bool(report.get("pass")) is False
    issue_keys = {str(i.get("key") or "") for i in (report.get("issues") or []) if isinstance(i, dict)}
    assert "trend_guard_failed" in issue_keys


def test_run_tool_adaptation_benchmark_schema_file_missing_fails_when_enforced(tmp_path: Path) -> None:
    repo_root = _find_repo_root(Path(__file__))
    output = tmp_path / "report.json"

    report = run_benchmark(
        repo_root=repo_root,
        output=output,
        min_score=0.0,
        schema_file=tmp_path / "not_exists_schema.json",
    )

    assert bool((report.get("schema_validation") or {}).get("ok")) is False
    assert bool(report.get("pass")) is False
