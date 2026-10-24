from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


def test_gate_writes_report_with_expected_schema(tmp_path) -> None:
    repo_root = Path(__file__).resolve().parents[2]
    report = tmp_path / "gate_report.json"
    env = dict(os.environ)
    env.setdefault("QUENTIN_MEMORY_STORE", "champion")
    env.setdefault("PG_HOST", "127.0.0.1")
    env.setdefault("PG_PORT", "55432")
    env.setdefault("PG_USER", "postgres")
    env.setdefault("PG_PASSWORD", "postgres")
    env.setdefault("PG_DB", "quentin_memory")
    env.setdefault("QDRANT_URL", "http://localhost:6333")
    env.setdefault("QUENTIN_QDRANT_WAIT_READY", "1")

    cp = subprocess.run(
        [
            sys.executable,
            str(repo_root / "scripts" / "run_brain_self_iteration_gate.py"),
            "--repo-root",
            str(repo_root),
            "--offline-smoke",
            "--timeout-sec",
            "240",
            "--report-out",
            str(report),
        ],
        cwd=str(repo_root),
        env=env,
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert cp.returncode in (0, 1), cp.stdout + cp.stderr
    obj = json.loads(report.read_text(encoding="utf-8"))
    assert isinstance(obj.get("ok"), bool)
    assert obj.get("strict_done") is True
    assert isinstance(obj.get("steps"), list)
    assert len(obj["steps"]) >= 3
