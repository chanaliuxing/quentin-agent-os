from __future__ import annotations

from pathlib import Path

from scripts.event_protocol_benchmark import run


def test_event_protocol_benchmark_report_has_split_scores(tmp_path: Path) -> None:
    out = run(tmp_path)
    assert isinstance(out, dict)
    assert isinstance(out.get("score_breakdown"), dict)
    parts = out["score_breakdown"]
    assert "capability_score" in parts
    assert "reliability_score" in parts
    assert "operations_score" in parts
    assert int(out.get("concurrency_events_count") or 0) >= 480
    checks = out.get("checks") or {}
    assert bool(checks.get("concurrency_session_seq_monotonic")) is True
    assert bool(checks.get("subscriber_stats_recorded")) is True
    assert bool(checks.get("rate_limit_observable_degrade")) is True
    assert int(out.get("failure_injection_cases") or 0) >= 20
