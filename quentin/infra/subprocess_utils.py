import asyncio
from typing import List, Tuple, Optional

from quentin.infra.concurrency.cancellation import CancellationToken, CancelledError


async def run_subprocess(
    cmd: List[str],
    cwd: Optional[str] = None,
    timeout: Optional[float] = None,
    cancel_token: Optional[CancellationToken] = None,
) -> Tuple[int, str, str]:
    """
    简单的 async 子进程封装：
    - 返回 (returncode, stdout, stderr)
    """
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        cwd=cwd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        communicate_task = asyncio.create_task(proc.communicate())
        cancel_task = None
        if cancel_token is not None:
            loop = asyncio.get_running_loop()
            cancel_task = loop.run_in_executor(None, cancel_token.wait)

        done, _pending = await asyncio.wait(
            {communicate_task, cancel_task} if cancel_task else {communicate_task},
            timeout=timeout,
            return_when=asyncio.FIRST_COMPLETED,
        )
        if cancel_task and cancel_task in done and not communicate_task.done():
            proc.terminate()
            try:
                await asyncio.wait_for(communicate_task, timeout=2)
            except asyncio.TimeoutError:
                proc.kill()
            raise CancelledError(cancel_token.reason() if cancel_token else "cancelled")
        if not communicate_task.done():
            proc.kill()
            raise asyncio.TimeoutError()
        out, err = communicate_task.result()
    except asyncio.TimeoutError:
        proc.kill()
        raise
    return proc.returncode, out.decode("utf-8", "ignore"), err.decode("utf-8", "ignore")
