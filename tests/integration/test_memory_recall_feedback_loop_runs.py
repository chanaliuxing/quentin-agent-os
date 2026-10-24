from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def test_run_memory_recall_feedback_loop_script_runs() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    script = repo_root / "scripts" / "run_memory_recall_feedback_loop.py"
    assert script.exists()

    proc = subprocess.run(
        [sys.executable, str(script), "--repo-root", str(repo_root)],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stdout + "\n" + proc.stderr
