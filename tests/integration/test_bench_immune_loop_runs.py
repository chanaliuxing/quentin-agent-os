from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def test_bench_immune_loop_script_runs(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[2]
    out_path = tmp_path / "immune_loop_bench.jsonl"
    proc = subprocess.run(
        [
            sys.executable,
            str(repo_root / "scripts" / "bench_immune_loop.py"),
            "--components",
            "2",
            "--traces-per",
            "10",
            "--runs",
            "1",
            "--out",
            str(out_path),
        ],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr[-2000:]
    assert out_path.exists()

