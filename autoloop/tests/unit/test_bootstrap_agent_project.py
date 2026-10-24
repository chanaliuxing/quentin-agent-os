from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def test_bootstrap_agent_project_creates_manifest(tmp_path: Path):
    root = Path(__file__).resolve().parents[2]
    target = tmp_path / "new_agent_project"
    script = root / "scripts" / "bootstrap_agent_project.py"
    completed = subprocess.run(
        [
            sys.executable,
            str(script),
            "--target-dir",
            str(target),
            "--project-id",
            "demo-agent",
        ],
        cwd=root,
        capture_output=True,
        text=True,
        check=True,
    )
    assert str(target) in completed.stdout
    assert (target / "project_manifest.txt").exists()
    assert (target / "policies" / "failure_router_policy.json").exists()
