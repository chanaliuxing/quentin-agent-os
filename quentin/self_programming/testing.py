# quentin/self_programming/testing.py
from __future__ import annotations

import logging
import subprocess
import time
from pathlib import Path
from typing import Optional, List, Dict, Any, Union

from quentin.self_programming.patches import (
    CodePatch,
    PatchTestCaseResult,
    PatchTestReport,
)
from quentin.utils.time import now_iso

logger = logging.getLogger(__name__)


class BasePatchTestRunner:
    """
    Patch 测试执行器接口。
    后续你可以实现不同 runner：
    - 调 pytest
    - 调 tox / nox
    - 调自定义脚本
    - 甚至在 Docker/K8s 里跑
    """

    def run_for_patch(self, patch: CodePatch) -> PatchTestReport:
        raise RuntimeError("BasePatchTestRunner is abstract; use ShellCommandPatchTestRunner or a concrete runner.")


class NoopPatchTestRunner(BasePatchTestRunner):
    """
    占位实现：标记“未执行任何测试”。
    用于本地还没配置测试时防止整个流程崩掉。
    """

    def run_for_patch(self, patch: CodePatch) -> PatchTestReport:
        report_id = f"{patch.patch_id}::tests::noop"
        case = PatchTestCaseResult(
            name="noop",
            status="not_run",
            duration_sec=None,
            error_message="No tests executed (NoopPatchTestRunner).",
            extra={},
        )
        report = PatchTestReport(
            report_id=report_id,
            patch_id=patch.patch_id,
            created_at=now_iso(), # Added created_at
            success=False,
            total_cases=1,
            passed=0,
            failed=0,
            errored=0,
            skipped=0,
            runtime_sec=None,
            static_analysis={},
            cases=[case],
        )
        return report


class ShellCommandPatchTestRunner(BasePatchTestRunner):
    """
    使用 shell 命令执行测试。
    默认命令：pytest -q

    注意：v1 并不会自动应用 CodePatch，只是针对当前代码库跑测试。
    以后可以在调用前后加上“临时应用补丁 + 回滚”的逻辑。
    """

    def __init__(
        self,
        repo_root: Union[str, Path] = ".",
        command: str = "pytest -q",
        env: Optional[Dict[str, str]] = None,
    ) -> None:
        self.repo_root = Path(repo_root)
        self.command = command
        self.env = env

    def run_for_patch(self, patch: CodePatch) -> PatchTestReport:
        report_id = f"{patch.patch_id}::tests::shell::{int(time.time())}"
        start_ts = time.perf_counter()

        case_name = f"shell:{self.command}"

        try:
            logger.info(
                "Running shell test command for patch %s: %s (cwd=%s)",
                patch.patch_id,
                self.command,
                self.repo_root,
            )
            proc = subprocess.run(
                self.command,
                shell=True,
                cwd=str(self.repo_root),
                env=self.env,
                capture_output=True,
                text=True,
            )
            end_ts = time.perf_counter()
            duration = end_ts - start_ts

            status = "passed" if proc.returncode == 0 else "failed"

            # 截断输出，避免 JSON 过大
            stdout = (proc.stdout or "")[:4000]
            stderr = (proc.stderr or "")[:4000]

            case = PatchTestCaseResult(
                name=case_name,
                status=status,
                duration_sec=duration,
                error_message=None if proc.returncode == 0 else (stderr or stdout),
                extra={
                    "returncode": proc.returncode,
                    "stdout_preview": stdout,
                    "stderr_preview": stderr,
                },
            )

            success = proc.returncode == 0
            report = PatchTestReport(
                report_id=report_id,
                patch_id=patch.patch_id,
                created_at=now_iso(), # Added created_at
                success=success,
                total_cases=1,
                passed=1 if success else 0,
                failed=0 if success else 1,
                errored=0,
                skipped=0,
                runtime_sec=duration,
                static_analysis={},
                cases=[case],
            )
            return report

        except Exception as e:
            end_ts = time.perf_counter()
            duration = end_ts - start_ts

            logger.exception("Error running shell test command for patch %s", patch.patch_id)
            case = PatchTestCaseResult(
                name=case_name,
                status="error",
                duration_sec=duration,
                error_message=str(e),
                extra={},
            )
            report = PatchTestReport(
                report_id=report_id,
                patch_id=patch.patch_id,
                created_at=now_iso(), # Added created_at
                success=False,
                total_cases=1,
                passed=0,
                failed=0,
                errored=1,
                skipped=0,
                runtime_sec=duration,
                static_analysis={},
                cases=[case],
            )
            return report
