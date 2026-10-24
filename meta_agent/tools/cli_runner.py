# meta_agent/tools/cli_runner.py
from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Dict, Optional
import json
import shlex
import subprocess
import time

from quentin.infra.concurrency.cancellation import CancellationToken


@dataclass
class CliResult:
    ok: bool
    result: Optional[Dict[str, Any]]
    logs: str
    error: Optional[str]
    raw_stdout: str
    raw_stderr: str


class JsonCliRunner:
    def __init__(self, cmd: str) -> None:
        self.cmd = shlex.split(cmd)

    def run(
        self,
        request: Dict[str, Any],
        timeout: int = 600,
        *,
        cancel_token: Optional[CancellationToken] = None,
    ) -> CliResult:
        try:
            proc = subprocess.Popen(  # noqa: S603,S607 - command is an explicit list
                self.cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
        except Exception as e:
            return CliResult(
                ok=False, result=None, logs="", error=f"subprocess_error: {e}",
                raw_stdout="", raw_stderr="",
            )

        started = time.perf_counter()
        input_bytes = json.dumps(request, ensure_ascii=False).encode("utf-8")
        input_arg: Optional[bytes] = input_bytes
        stdout_b = b""
        stderr_b = b""
        try:
            while True:
                if cancel_token is not None and cancel_token.is_cancelled():
                    proc.terminate()
                    try:
                        stdout_b, stderr_b = proc.communicate(timeout=2)
                    except Exception:
                        proc.kill()
                        stdout_b, stderr_b = proc.communicate()
                    return CliResult(
                        ok=False,
                        result=None,
                        logs="",
                        error=f"cancelled: {cancel_token.reason() or 'cancelled'}",
                        raw_stdout=(stdout_b or b"").decode("utf-8", errors="ignore"),
                        raw_stderr=(stderr_b or b"").decode("utf-8", errors="ignore"),
                    )

                remaining = max(0.0, float(timeout) - (time.perf_counter() - started))
                if remaining <= 0.0:
                    proc.kill()
                    stdout_b, stderr_b = proc.communicate()
                    return CliResult(
                        ok=False,
                        result=None,
                        logs="",
                        error="timeout",
                        raw_stdout=(stdout_b or b"").decode("utf-8", errors="ignore"),
                        raw_stderr=(stderr_b or b"").decode("utf-8", errors="ignore"),
                    )

                try:
                    stdout_b, stderr_b = proc.communicate(input=input_arg, timeout=min(0.2, remaining))
                    break
                except subprocess.TimeoutExpired:
                    # After the first communicate attempt, the input was already provided by Python.
                    # Ensure we don't try to re-send it.
                    input_arg = None
                    continue
        except Exception as e:
            try:
                proc.kill()
            except Exception:
                pass
            return CliResult(
                ok=False, result=None, logs="", error=f"subprocess_error: {e}",
                raw_stdout=(stdout_b or b"").decode("utf-8", errors="ignore"),
                raw_stderr=(stderr_b or b"").decode("utf-8", errors="ignore"),
            )

        stdout = (stdout_b or b"").decode("utf-8", errors="ignore")
        stderr = (stderr_b or b"").decode("utf-8", errors="ignore")

        if proc.returncode != 0:
            return CliResult(
                ok=False, result=None, logs=stderr, error=f"exit_code={proc.returncode}",
                raw_stdout=stdout, raw_stderr=stderr,
            )

        try:
            data = json.loads(stdout)
        except Exception as e:
            return CliResult(
                ok=False, result=None, logs=stderr, error=f"json_decode_error: {e}",
                raw_stdout=stdout, raw_stderr=stderr,
            )

        return CliResult(
            ok=bool(data.get("ok", True)),
            result=data.get("result"),
            logs=data.get("logs") or "",
            error=data.get("error"),
            raw_stdout=stdout,
            raw_stderr=stderr,
        )
