from pathlib import Path
from typing import Dict, Any, List, Optional
from quentin.infra.subprocess_utils import run_subprocess
from quentin.infra.concurrency.cancellation import CancellationToken


class TestRunner:
    """
    通用测试执行器：
    - patch.test_commands 不为空时，按顺序在 repo 根目录执行
    - 为空则认为「无测试」（ok=True, tests_skipped=True）
    """

    async def run_tests(
        self,
        repo_root: Path,
        test_commands: List[str],
        cancel_token: Optional[CancellationToken] = None,
    ) -> Dict[str, Any]:
        if not test_commands:
            return {"ok": True, "tests_skipped": True}

        all_ok = True
        details = []
        for cmd_str in test_commands:
            # 简单地按 shell 分词（研究/生产中建议用更严格解析）
            parts = cmd_str.split()
            kwargs: Dict[str, Any] = {"cwd": str(repo_root), "timeout": 300.0}
            if cancel_token is not None:
                kwargs["cancel_token"] = cancel_token
            code, out, err = await run_subprocess(parts, **kwargs)
            ok = code == 0
            all_ok = all_ok and ok
            details.append(
                {
                    "cmd": cmd_str,
                    "returncode": code,
                    "stdout": out,
                    "stderr": err,
                }
            )

        return {"ok": all_ok, "details": details}
