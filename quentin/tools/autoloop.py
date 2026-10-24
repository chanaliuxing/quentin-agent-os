from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict


def autoloop_run(params: Dict[str, Any], context: Any = None) -> Dict[str, Any]:
    _ = context
    prd_path = str(params.get("prd_path") or "").strip()
    if not prd_path:
        return {
            "status": "error",
            "error": "missing_prd_path",
            "hint": "Provide params.prd_path (absolute or repo-relative).",
        }

    mode = str(params.get("mode") or "temporal").strip()
    profile = str(params.get("profile") or "dev").strip()
    project_id = str(params.get("project_id") or "").strip()
    dry_run = bool(params.get("dry_run", True))

    try:
        timeout_seconds = int(params.get("timeout_seconds", 1800) or 1800)
    except Exception:
        timeout_seconds = 1800

    repo_root = Path(__file__).resolve().parents[2]
    autoloop_root = repo_root / "autoloop"
    if not autoloop_root.exists():
        return {
            "status": "error",
            "error": "autoloop_not_found",
            "path": str(autoloop_root),
        }

    resolved_prd = Path(prd_path)
    if not resolved_prd.is_absolute():
        resolved_prd = (repo_root / resolved_prd).resolve()
    if not resolved_prd.exists():
        return {
            "status": "error",
            "error": "prd_not_found",
            "prd_path": str(resolved_prd),
        }

    cmd = [sys.executable, "-m", "app.main", "run", str(resolved_prd), "--mode", mode, "--profile", profile]
    if project_id:
        cmd.extend(["--project-id", project_id])

    env = dict(os.environ)
    if "TEMPORAL_MOCK_MODE" not in env:
        env["TEMPORAL_MOCK_MODE"] = "true"

    if dry_run:
        return {
            "status": "ok",
            "dry_run": True,
            "cwd": str(autoloop_root),
            "command": cmd,
            "timeout_seconds": timeout_seconds,
            "env_overrides": {"TEMPORAL_MOCK_MODE": env.get("TEMPORAL_MOCK_MODE", "")},
        }

    started = time.time()
    try:
        cp = subprocess.run(
            cmd,
            cwd=str(autoloop_root),
            env=env,
            capture_output=True,
            text=True,
            timeout=max(1, timeout_seconds),
        )
    except subprocess.TimeoutExpired as e:
        return {
            "status": "error",
            "error": "timeout",
            "timed_out": True,
            "timeout_seconds": timeout_seconds,
            "stdout_tail": str(e.stdout or "")[-4000:],
            "stderr_tail": str(e.stderr or "")[-4000:],
            "duration_sec": round(time.time() - started, 3),
        }

    return {
        "status": "ok" if int(cp.returncode) == 0 else "error",
        "returncode": int(cp.returncode),
        "timed_out": False,
        "duration_sec": round(time.time() - started, 3),
        "stdout_tail": str(cp.stdout or "")[-4000:],
        "stderr_tail": str(cp.stderr or "")[-4000:],
        "command": cmd,
        "cwd": str(autoloop_root),
    }
