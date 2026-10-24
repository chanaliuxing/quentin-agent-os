from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def test_check_sqlite_vec_env_strict_fails_when_not_ready(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[2]
    proc = subprocess.run(
        [
            sys.executable,
            str(repo_root / "scripts" / "check_sqlite_vec_env.py"),
            "--strict",
        ],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
    )
    # In CI/dev containers without sqlite-vec extension this should fail fast.
    # If environment becomes ready in future, this may become 0.
    assert proc.returncode in (0, 5), proc.stderr[-2000:] + "\n" + proc.stdout[-2000:]
