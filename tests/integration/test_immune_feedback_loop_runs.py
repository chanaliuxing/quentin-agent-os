from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def test_immune_loop_feedback_loop_script_runs() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    proc = subprocess.run(
        [sys.executable, str(repo_root / "scripts" / "run_immune_loop_feedback_loop.py")],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr[-2000:]

