from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def test_bench_memory_intelligence_script_runs(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[2]
    out = tmp_path / "intelligence_bench.jsonl"
    db_dir = tmp_path / "db"
    db_dir.mkdir(parents=True, exist_ok=True)

    proc = subprocess.run(
        [
            sys.executable,
            str(repo_root / "scripts" / "bench_memory_intelligence.py"),
            "--backend",
            "sqlite",
            "--n",
            "120",
            "--modes",
            "text_only,hybrid",
            "--cases",
            "8",
            "--runs",
            "1",
            "--warmup",
            "0",
            "--dim",
            "32",
            "--top-k",
            "5",
            "--db-dir",
            str(db_dir),
            "--out",
            str(out),
        ],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr[-2000:] + "\n" + proc.stdout[-2000:]
    assert out.exists()

    rows = [json.loads(x) for x in out.read_text(encoding="utf-8").splitlines() if x.strip()]
    assert rows, "no benchmark rows written"
    required = {
        "task_success_rate",
        "first_hit_useful_rate",
        "error_recurrence_rate",
        "memory_pollution_rate",
        "intelligence_score",
    }
    for row in rows:
        assert required.issubset(row.keys()), row
