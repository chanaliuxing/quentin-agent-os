from __future__ import annotations

import json
from pathlib import Path

from scripts.planning_threshold_env_patch import build_env_patch, run


def test_build_env_patch_maps_thresholds_and_fallback_bucket() -> None:
    report = {
        "buckets": {
            "global": {
                "thresholds": {
                    "strategy_switch_effectiveness": 0.61,
                    "interrupt_effectiveness": 0.66,
                    "reset_recovery_rate": 0.53,
                    "progress_sync_compliance": 0.82,
                    "attempt_band_coverage": 0.79,
                }
            }
        }
    }
    out = build_env_patch(recommendation_report=report, bucket="maintenance")
    assert out["requested_bucket"] == "maintenance"
    assert out["used_bucket"] == "global"
    mapped = out["mapped_thresholds"]
    assert float(mapped["QUENTIN_VERIFY_STRATEGY_SWITCH_MIN"]) == 0.61
    assert float(mapped["QUENTIN_VERIFY_ATTEMPT_BAND_COVERAGE_MIN"]) == 0.79
    lines = "\n".join(out["lines"])
    assert "QUENTIN_VERIFY_AUTOCALIBRATE_DOMAIN_BUCKET=global" in lines
    assert "QUENTIN_VERIFY_RESET_RECOVERY_MIN=0.530" in lines


def test_run_writes_env_patch_file(tmp_path: Path) -> None:
    recommendation = tmp_path / "recommendation.json"
    output = tmp_path / "threshold_patch.env"
    recommendation.write_text(
        json.dumps(
            {
                "buckets": {
                    "research": {
                        "thresholds": {
                            "strategy_switch_effectiveness": 0.58,
                            "interrupt_effectiveness": 0.62,
                        }
                    }
                }
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    out = run(recommendation_path=recommendation, output_path=output, bucket="research")
    assert out["used_bucket"] == "research"
    assert output.exists()
    body = output.read_text(encoding="utf-8")
    assert "QUENTIN_VERIFY_STRATEGY_SWITCH_MIN=0.580" in body
    assert "QUENTIN_VERIFY_INTERRUPT_EFFECTIVENESS_MIN=0.620" in body
