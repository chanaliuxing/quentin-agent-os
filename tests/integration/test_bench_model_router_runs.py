from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def test_bench_model_router_script_runs() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    script = repo_root / "scripts" / "bench_model_router.py"
    assert script.exists()

    proc = subprocess.run(
        [sys.executable, str(script), "--repo-root", str(repo_root), "--iters", "200"],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stdout + "\n" + proc.stderr

    # Script prints a single JSON line.
    data = json.loads(proc.stdout.strip().splitlines()[-1])
    assert data["benchmark"] == "model_router.choose_model"
    assert int(data["iters"]) == 200
