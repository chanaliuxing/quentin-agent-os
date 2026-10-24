from __future__ import annotations

import json
from pathlib import Path

from scripts.execution_layer_benchmark import BenchThresholds, BenchmarkConfig, compute_execution_score, run_benchmark


def test_compute_execution_score_contract() -> None:
    report = {
        "metrics": {
            "web_readability": {"p95_ms": 10.0},
            "image_tool": {"p95_ms": 50.0},
            "canvas_tool": {"p95_ms": 10.0},
            "nodes_tool": {"p95_ms": 10.0},
            "cron_tool": {"p95_ms": 10.0},
            "session_status": {"p95_ms": 10.0},
            "observability_overview": {"p95_ms": 50.0},
        },
        "checks": {
            "correctness": {"results": [{"passed": True}, {"passed": False}]},
            "robustness": {"results": [{"passed": True}]},
            "observability": {"results": [{"passed": True}, {"passed": True}]},
        },
    }
    out = compute_execution_score(report, BenchThresholds())
    assert 0.0 <= float(out.get("overall") or 0.0) <= 1.0
    assert 0.0 <= float(out.get("performance") or 0.0) <= 1.0
    assert float(out.get("correctness") or 0.0) == 0.5


def test_run_benchmark_writes_report_and_history(tmp_path: Path) -> None:
    output = tmp_path / "generated" / "benchmarks" / "exec_report.json"
    history = tmp_path / "generated" / "benchmarks" / "exec_history.jsonl"
    cfg = BenchmarkConfig(
        iters=3,
        concurrency=2,
        stress_dead_letters=10,
        stress_lease_events=10,
        stress_canvas_components=5,
        seed=13,
    )
    report = run_benchmark(
        repo_root=tmp_path,
        output=output,
        history=history,
        previous=None,
        config=cfg,
        keep_workdir=True,
        min_overall_score=0.0,
    )
    assert output.exists()
    assert history.exists()
    data = json.loads(output.read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    assert "scores" in data and isinstance(data["scores"], dict)
    assert bool(data.get("pass")) is True
    assert int((data.get("checks") or {}).get("correctness", {}).get("total") or 0) >= 1

