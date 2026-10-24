from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def test_arch_ci_gate_passes() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    gate = repo_root / "scripts" / "qa" / "arch_ci_gate.py"
    allowlist = repo_root / "config" / "arch_ci_gate_allowlist.json"
    assert gate.exists(), f"missing gate script: {gate}"
    assert allowlist.exists(), f"missing allowlist: {allowlist}"

    proc = subprocess.run(
        [
            sys.executable,
            str(gate),
            "--repo-root",
            str(repo_root),
            "--allowlist",
            str(allowlist),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, (proc.stdout + "\n" + proc.stderr).strip()
    payload = json.loads(proc.stdout.strip())
    assert payload.get("ok") is True

