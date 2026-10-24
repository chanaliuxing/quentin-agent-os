from __future__ import annotations

import json
from pathlib import Path

from scripts.planning_threshold_recommendation import recommend_thresholds, run


def test_recommend_thresholds_by_bucket_and_fallback() -> None:
    rows = []
    for _ in range(10):
        rows.append(
            {
                "calibration_bucket": {"domain": "global"},
                "score_components": {
                    "strategy_switch_effectiveness": 0.70,
                    "interrupt_effectiveness": 0.72,
                    "reset_recovery_rate": 0.68,
                    "progress_sync_compliance": 0.85,
                },
                "intelligence_audit": {"strategy_regression": {"strategy_switching": {"attempt_band_coverage": 0.84}}},
            }
        )
    for _ in range(4):
        rows.append(
            {
                "calibration_bucket": {"domain": "research"},
                "score_components": {
                    "strategy_switch_effectiveness": 0.45,
                    "interrupt_effectiveness": 0.50,
                    "reset_recovery_rate": 0.48,
                    "progress_sync_compliance": 0.70,
                },
                "intelligence_audit": {"strategy_regression": {"strategy_switching": {"attempt_band_coverage": 0.75}}},
            }
        )

    out = recommend_thresholds(rows=rows, min_samples=8, quantile=0.30)
    buckets = out.get("buckets") or {}
    assert "global" in buckets
    assert "research" in buckets
    assert buckets["research"]["fallback_to_global"] is True
    assert float(buckets["global"]["thresholds"]["strategy_switch_effectiveness"]) > 0.60


def test_run_writes_recommendation_file(tmp_path: Path) -> None:
    hist = tmp_path / "history.jsonl"
    out = tmp_path / "recommend.json"
    with hist.open("w", encoding="utf-8") as f:
        for _ in range(8):
            row = {
                "calibration_bucket": {"domain": "maintenance"},
                "score_components": {
                    "strategy_switch_effectiveness": 0.62,
                    "interrupt_effectiveness": 0.67,
                    "reset_recovery_rate": 0.58,
                    "progress_sync_compliance": 0.82,
                },
                "intelligence_audit": {"strategy_regression": {"strategy_switching": {"attempt_band_coverage": 0.81}}},
            }
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    report = run(history=hist, output=out, min_samples=8, quantile=0.30)
    assert out.exists()
    assert (report.get("buckets") or {}).get("maintenance") is not None
