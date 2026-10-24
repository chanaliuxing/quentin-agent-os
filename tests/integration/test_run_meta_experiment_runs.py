from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def test_run_meta_experiment_script_runs() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    script = repo_root / "scripts" / "run_meta_experiment.py"
    assert script.exists()

    proc = subprocess.run(
        [
            sys.executable,
            str(script),
            "--repo-root",
            str(repo_root),
            "--experiment-id",
            "test_meta_exp",
            "--metrics-file",
            "data/research/test_meta_experiment_metrics.jsonl",
            "--out",
            "data/experiments/test_meta_experiment_result.json",
            "--task-limit-per-variant",
            "1",
            "--time-window-hours",
            "0",
        ],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stdout + "\n" + proc.stderr

    summary = json.loads(proc.stdout.strip().splitlines()[-1])
    assert summary.get("experiment_id") == "test_meta_exp"
    assert "out" in summary
