from __future__ import annotations

import logging
import subprocess
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, Optional

from quentin.self_programming.patches import CodePatch

logger = logging.getLogger(__name__)


@dataclass
class PatchEvalMetrics:
    """
    Summary of one patch evaluation run.
    """

    success: bool
    test_command: str
    exit_code: int
    duration_sec: float
    stdout_tail: str
    stderr_tail: str
    notes: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class PatchEvalHarness:
    """
    Minimal patch test harness.

    Notes:
    - Does not apply the patch; assumes caller already applied it in `repo_root`.
    - Only runs a shell `test_command` (default: pytest).
    """

    def __init__(
        self,
        repo_root: str | Path = ".",
        test_command: str = "pytest",
        max_output_chars: int = 4000,
    ) -> None:
        self.repo_root = Path(repo_root)
        self.test_command = test_command
        self.max_output_chars = max_output_chars

    def evaluate_patch(self, patch: CodePatch, *, apply_notes: Optional[str] = None) -> PatchEvalMetrics:
        cmd = self.test_command
        t0 = time.time()
        try:
            proc = subprocess.run(
                cmd,
                cwd=str(self.repo_root),
                shell=True,
                capture_output=True,
                text=True,
            )
            duration = time.time() - t0
        except Exception as e:  # noqa: BLE001
            logger.exception("PatchEvalHarness: failed to run tests for patch %s", getattr(patch, "patch_id", "unknown"))
            return PatchEvalMetrics(
                success=False,
                test_command=cmd,
                exit_code=-1,
                duration_sec=time.time() - t0,
                stdout_tail="",
                stderr_tail=f"Exception when running tests: {e}",
                notes="test_command failed to execute",
            )

        stdout = proc.stdout or ""
        stderr = proc.stderr or ""

        def _tail(s: str) -> str:
            if len(s) <= self.max_output_chars:
                return s
            return s[-self.max_output_chars :]

        return PatchEvalMetrics(
            success=(proc.returncode == 0),
            test_command=cmd,
            exit_code=int(proc.returncode),
            duration_sec=float(duration),
            stdout_tail=_tail(stdout),
            stderr_tail=_tail(stderr),
            notes=apply_notes or "",
        )

