from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def test_run_memory_intelligence_scale_matrix_runs(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[2]
    out_dir = tmp_path / "out"
    db_dir = tmp_path / "db"
    out_dir.mkdir(parents=True, exist_ok=True)
    db_dir.mkdir(parents=True, exist_ok=True)

    proc = subprocess.run(
        [
            sys.executable,
            str(repo_root / "scripts" / "run_memory_intelligence_scale_matrix.py"),
            "--backend",
            "sqlite",
            "--n",
            "120",
            "--modes",
            "hybrid",
            "--case-profile",
            "mixed",
            "--query-domain-policy",
            "case",
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
            "--out-dir",
            str(out_dir),
            "--timeout-s",
            "120",
        ],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr[-2000:] + "\n" + proc.stdout[-2000:]

    summary = out_dir / "scale_summary.json"
    assert summary.exists()
    data = json.loads(summary.read_text(encoding="utf-8"))
    runs = data.get("runs") or []
    assert runs
    assert int(runs[0].get("n", 0)) == 120


def test_run_memory_intelligence_scale_matrix_lock_busy(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[2]
    out_dir = tmp_path / "out"
    db_dir = tmp_path / "db"
    lock_file = tmp_path / ".lock"
    out_dir.mkdir(parents=True, exist_ok=True)
    db_dir.mkdir(parents=True, exist_ok=True)
    lock_file.write_text("busy", encoding="utf-8")

    proc = subprocess.run(
        [
            sys.executable,
            str(repo_root / "scripts" / "run_memory_intelligence_scale_matrix.py"),
            "--backend",
            "sqlite",
            "--n",
            "120",
            "--modes",
            "hybrid",
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
            "--out-dir",
            str(out_dir),
            "--timeout-s",
            "120",
            "--lock-file",
            str(lock_file),
            "--lock-timeout-s",
            "0",
        ],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 9, proc.stderr[-2000:] + "\n" + proc.stdout[-2000:]
