from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def test_bench_memory_recall_require_index_backend_fails_without_sqlite_vec(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[2]
    out_path = tmp_path / "recall_bench.jsonl"
    db_dir = tmp_path / "db"
    db_dir.mkdir(parents=True, exist_ok=True)

    proc = subprocess.run(
        [
            sys.executable,
            str(repo_root / "scripts" / "bench_memory_recall.py"),
            "--backend",
            "sqlite_vec",
            "--n",
            "20",
            "--modes",
            "vector_only",
            "--runs",
            "1",
            "--warmup",
            "0",
            "--db-dir",
            str(db_dir),
            "--out",
            str(out_path),
            "--require-index-backend",
        ],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 3
