from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def test_rebaseline_memory_slo_script_runs(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[2]
    bench = tmp_path / "bench.jsonl"
    rows = [
        {
            "ts_utc": "2026-01-01T00:00:00+00:00",
            "n_records": 10000,
            "mode": "text_only",
            "backend": "sqlite_vec",
            "vector_backend": "sqlite_vec",
            "avg_ms": 10.0,
            "p95_ms": 20.0,
            "hit_rate_at_k": 1.0,
        },
        {
            "ts_utc": "2026-01-01T00:00:00+00:00",
            "n_records": 10000,
            "mode": "vector_only",
            "backend": "sqlite_vec",
            "vector_backend": "sqlite_vec",
            "avg_ms": 40.0,
            "p95_ms": 80.0,
            "hit_rate_at_k": 0.95,
        },
        {
            "ts_utc": "2026-01-01T00:00:00+00:00",
            "n_records": 10000,
            "mode": "hybrid",
            "backend": "sqlite_vec",
            "vector_backend": "sqlite_vec",
            "avg_ms": 50.0,
            "p95_ms": 100.0,
            "hit_rate_at_k": 0.9,
        },
    ]
    with bench.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    out = tmp_path / "slo.generated.json"
    proc = subprocess.run(
        [
            sys.executable,
            str(repo_root / "scripts" / "rebaseline_memory_slo.py"),
            "--in",
            str(bench),
            "--out",
            str(out),
            "--tiers",
            "10000",
            "--backend",
            "sqlite_vec",
            "--vector-backend",
            "sqlite_vec",
        ],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr[-2000:] + "\n" + proc.stdout[-2000:]
    assert out.exists()
    obj = json.loads(out.read_text(encoding="utf-8"))
    assert "10000" in (obj.get("tiers") or {})
    modes = ((obj.get("tiers") or {}).get("10000") or {}).get("modes") or {}
    assert "text_only" in modes
    assert "vector_only" in modes
    assert "hybrid" in modes


def test_rebaseline_memory_slo_fail_on_empty(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[2]
    bench = tmp_path / "bench_empty.jsonl"
    bench.write_text("", encoding="utf-8")
    out = tmp_path / "slo.empty.json"

    proc = subprocess.run(
        [
            sys.executable,
            str(repo_root / "scripts" / "rebaseline_memory_slo.py"),
            "--in",
            str(bench),
            "--out",
            str(out),
            "--fail-on-empty",
        ],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 4
