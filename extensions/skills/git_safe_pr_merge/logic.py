from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional


REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT_PATH = REPO_ROOT / "scripts" / "git_safe_flow.sh"


def _append_opt(cmd: List[str], key: str, value: Any) -> None:
    if value is None:
        return
    text = str(value).strip()
    if text:
        cmd.extend([key, text])


def _append_flag(cmd: List[str], key: str, enabled: Any) -> None:
    if bool(enabled):
        cmd.append(key)


def run(inputs: Dict[str, Any], ctx: Optional[Any] = None) -> Dict[str, Any]:
    _ = ctx
    payload = inputs or {}
    cmd: List[str] = ["bash", str(SCRIPT_PATH)]

    _append_opt(cmd, "--repo", payload.get("repo"))
    _append_opt(cmd, "--base", payload.get("base"))
    _append_opt(cmd, "--unit-cmd", payload.get("unit_cmd"))
    _append_opt(cmd, "--regression-cmd", payload.get("regression_cmd"))
    _append_opt(cmd, "--commit-msg", payload.get("commit_msg"))
    _append_opt(cmd, "--pr-title", payload.get("pr_title"))
    _append_opt(cmd, "--pr-body", payload.get("pr_body"))
    _append_opt(cmd, "--merge-method", payload.get("merge_method"))
    _append_opt(cmd, "--create-worktree", payload.get("create_worktree"))
    _append_opt(cmd, "--worktree-path", payload.get("worktree_path"))
    _append_opt(cmd, "--branch", payload.get("branch"))

    _append_flag(cmd, "--auto-stage", payload.get("auto_stage", False))
    _append_flag(cmd, "--allow-existing-commits", payload.get("allow_existing_commits", False))
    _append_flag(cmd, "--disable-auto-merge", payload.get("disable_auto_merge", False))
    _append_flag(cmd, "--merge-now", payload.get("merge_now", False))
    _append_flag(cmd, "--execute", payload.get("execute", False))

    if not SCRIPT_PATH.exists():
        return {
            "status": "error",
            "error": f"script not found: {SCRIPT_PATH}",
            "cmd": cmd,
        }

    proc = subprocess.run(cmd, cwd=str(REPO_ROOT), capture_output=True, text=True)
    ok = proc.returncode == 0
    return {
        "status": "ok" if ok else "error",
        "code": proc.returncode,
        "cmd": cmd,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
    }
