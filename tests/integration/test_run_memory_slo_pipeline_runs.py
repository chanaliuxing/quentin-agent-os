from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def test_run_memory_slo_pipeline_script_runs(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[2]
    bench_out = tmp_path / "bench.jsonl"
    slo_in = tmp_path / "slo.in.json"
    slo_out = tmp_path / "slo.out.json"
    db_dir = tmp_path / "db"
    db_dir.mkdir(parents=True, exist_ok=True)

    slo_in.write_text(
        json.dumps(
            {
                "tiers": {
                    "30": {
                        "modes": {
                            "text_only": {"p95_ms_max": 5000.0, "avg_ms_max": 5000.0, "hit_rate_at_k_min": 0.0},
                            "vector_only": {"p95_ms_max": 5000.0, "avg_ms_max": 5000.0, "hit_rate_at_k_min": 0.0},
                            "hybrid": {"p95_ms_max": 5000.0, "avg_ms_max": 5000.0, "hit_rate_at_k_min": 0.0},
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
            str(repo_root / "scripts" / "run_memory_slo_pipeline.py"),
            "--backend",
            "sqlite",
            "--vector-backend",
            "client_scan",
            "--n",
            "30",
            "--tiers",
            "30",
            "--runs",
            "1",
            "--warmup",
            "0",
            "--dim",
            "16",
            "--top-k",
            "5",
            "--db-dir",
            str(db_dir),
            "--bench-out",
            str(bench_out),
            "--slo-in",
            str(slo_in),
            "--slo-out",
            str(slo_out),
        ],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr[-2000:] + "\n" + proc.stdout[-2000:]
    assert bench_out.exists()
    assert slo_out.exists()
    obj = json.loads(slo_out.read_text(encoding="utf-8"))
    assert "30" in (obj.get("tiers") or {})
