from __future__ import annotations

from quentin.benchmarks.session_model import run_benchmark


def test_session_model_benchmark_report_shape(tmp_path) -> None:
    report = run_benchmark(repo_root=tmp_path)
    assert report.get("benchmark") == "session_model"
    assert isinstance(report.get("quality_score"), float)
    assert isinstance(report.get("checks"), dict)
    assert "session_recovery" in report["checks"]
    assert "compaction_stateful" in report["checks"]
    assert "lane_abort_binding" in report["checks"]
    assert "delta_state_bridge" in report["checks"]


def test_session_model_benchmark_passes(tmp_path) -> None:
    report = run_benchmark(repo_root=tmp_path)
    assert report.get("pass") is True
    assert float(report.get("quality_score") or 0.0) >= 1.0
