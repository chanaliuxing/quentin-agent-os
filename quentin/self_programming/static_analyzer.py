from pathlib import Path
from typing import Dict, Any, Optional
from quentin.infra.subprocess_utils import run_subprocess
from quentin.infra.concurrency.cancellation import CancellationToken


class StaticAnalyzer:
    """
    最基础的静态检查：
    - 使用 python -m py_compile 做语法检查
    - 将来可以接入 ruff / mypy 等更高级工具
    """

    async def run_checks(
        self,
        module_path: Path,
        cancel_token: Optional[CancellationToken] = None,
    ) -> Dict[str, Any]:
        kwargs: Dict[str, Any] = {"cwd": str(module_path.parent), "timeout": 30.0}
        if cancel_token is not None:
            kwargs["cancel_token"] = cancel_token
        code, out, err = await run_subprocess(["python", "-m", "py_compile", str(module_path)], **kwargs)
        return {
            "ok": code == 0,
            "returncode": code,
            "stdout": out,
            "stderr": err,
        }
