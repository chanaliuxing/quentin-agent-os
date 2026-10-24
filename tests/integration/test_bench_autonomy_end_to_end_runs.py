from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def test_bench_autonomy_end_to_end_runs(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[2]
    out_path = tmp_path / "autonomy_bench.json"

    proc = subprocess.run(
        [
            sys.executable,
            str(repo_root / "scripts" / "bench_autonomy_end_to_end.py"),
            "--max-tasks",
            "2",
            "--out",
            str(out_path),
        ],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr[-2000:]
    assert out_path.exists()

