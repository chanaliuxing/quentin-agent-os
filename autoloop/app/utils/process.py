import asyncio
import psutil
from pathlib import Path
from typing import Any


async def run_subprocess_with_timeout(
    cmd: list[str],
    cwd: str,
    timeout: int,
    log_file: Path,
    env: dict[str, str] | None = None,
    stdin_input: str | None = None,
) -> dict[str, Any]:
    log_file.parent.mkdir(parents=True, exist_ok=True)

    import os
    full_env = os.environ.copy()
    if env:
        full_env.update(env)

    process = await asyncio.create_subprocess_exec(
        *cmd,
        cwd=cwd,
        stdin=asyncio.subprocess.PIPE if stdin_input is not None else None,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=full_env,
        start_new_session=True,
    )

    try:
        stdin_bytes = (
            stdin_input.encode("utf-8", errors="replace")
            if stdin_input is not None
            else None
        )
        stdout, stderr = await asyncio.wait_for(process.communicate(stdin_bytes), timeout=timeout)

        stdout_text = stdout.decode("utf-8", errors="replace")
        stderr_text = stderr.decode("utf-8", errors="replace")

        with open(log_file, "w") as f:
            f.write("=== STDOUT ===\n")
            f.write(stdout_text)
            f.write("\n=== STDERR ===\n")
            f.write(stderr_text)

        return {
            "returncode": process.returncode,
            "stdout": stdout_text,
            "stderr": stderr_text,
        }

    except asyncio.TimeoutError:
        await kill_process_tree(process.pid)
        raise


async def kill_process_tree(pid: int | None, timeout: int = 5) -> None:
    if pid is None:
        return

    try:
        import os
        try:
            os.killpg(pid, 15)
        except Exception:
            pass
        parent = psutil.Process(pid)
        children = parent.children(recursive=True)

        for child in children:
            try:
                child.terminate()
            except psutil.NoSuchProcess:
                pass

        try:
            parent.terminate()
        except psutil.NoSuchProcess:
            pass

        gone, alive = psutil.wait_procs(children + [parent], timeout=timeout)

        for p in alive:
            try:
                p.kill()
            except psutil.NoSuchProcess:
                pass
        try:
            os.killpg(pid, 9)
        except Exception:
            pass

    except psutil.NoSuchProcess:
        pass
    except Exception as e:
        print(f"Error killing process tree: {e}")
