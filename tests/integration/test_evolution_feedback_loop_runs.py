from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def test_run_evolution_feedback_loop_script_runs() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    script = repo_root / "scripts" / "run_evolution_feedback_loop.py"
    assert script.exists()

    # Keep artifacts under data/ (ignored) and ensure uniqueness across runs.
    proc = subprocess.run(
        [
            sys.executable,
            str(script),
            "--repo-root",
            str(repo_root),
            "--kv-path",
            "data/research/test_model_router_kv.sqlite3",
            "--rules-path",
            "data/research/test_model_router_rules.json",
            "--domain",
            "desktop",
            "--environment",
            "sandbox",
        ],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stdout + "\n" + proc.stderr
