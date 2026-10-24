from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def test_run_blueprint_v3_1_landing_dry_run_generates_report(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[2]
    report = tmp_path / "landing_report.json"
    proc = subprocess.run(
        [
            sys.executable,
            str(repo_root / "scripts" / "run_blueprint_v3_1_landing.py"),
            "--dry-run",
            "--quick",
            "--report-out",
            str(report),
        ],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr[-2000:] + "\n" + proc.stdout[-2000:]
    assert report.exists()
    obj = json.loads(report.read_text(encoding="utf-8"))
    assert obj.get("ok") is True
    steps = obj.get("steps") or []
    assert len(steps) == 8
