from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def test_bench_memory_recall_script_slo_check_runs(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[2]
    out_path = tmp_path / "recall_bench.jsonl"
    db_dir = tmp_path / "db"
    db_dir.mkdir(parents=True, exist_ok=True)
    slo_path = tmp_path / "slo.json"
    slo_path.write_text(
        json.dumps(
            {
                "tiers": {
                    "10": {
                        "modes": {
                            "text_only": {"p95_ms_max": 5000.0, "hit_rate_at_k_min": 0.0},
                            "vector_only": {"p95_ms_max": 5000.0, "hit_rate_at_k_min": 0.0},
                            "hybrid": {"p95_ms_max": 5000.0, "hit_rate_at_k_min": 0.0},
                        }
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    proc = subprocess.run(
        [
            sys.executable,
            str(repo_root / "scripts" / "bench_memory_recall.py"),
            "--backend",
            "sqlite",
            "--n",
            "30",
            "--modes",
            "text_only,vector_only,hybrid",
            "--runs",
            "1",
            "--warmup",
            "0",
            "--db-dir",
            str(db_dir),
            "--out",
            str(out_path),
            "--slo-file",
            str(slo_path),
            "--fail-on-slo",
        ],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr[-2000:] + "\n" + proc.stdout[-2000:]
    assert out_path.exists()
