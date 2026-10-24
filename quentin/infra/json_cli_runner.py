from __future__ import annotations
import asyncio
import json
import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from quentin.infra import subprocess_utils
from quentin.infra.concurrency.cancellation import CancellationToken, CancelledError
# Expose run_subprocess for tests to patch
run_subprocess = subprocess_utils.run_subprocess

logger = logging.getLogger(__name__)

@dataclass
class CliResult:
    """
    Standardized result for CLI command executions.
    """
    command: List[str]
    ok: bool
    return_code: int
    raw_stdout: str
    raw_stderr: str
    parsed_json: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None
    timeout: Optional[float] = None

class JsonCliRunner:
    """
    A utility to run external CLI commands and parse their JSON output.
    """
    def __init__(self, cwd: Optional[str] = None, default_timeout: Optional[float] = 60.0):
        self.cwd = cwd
        self.default_timeout = default_timeout

    async def run(
        self,
        cmd: List[str],
        timeout: Optional[float] = None,
        cancel_token: Optional[CancellationToken] = None,
    ) -> CliResult:
        """
        Runs a CLI command, attempts to parse its stdout as JSON.
        """
        final_timeout = timeout if timeout is not None else self.default_timeout
        
        try:
            kwargs: Dict[str, Any] = {"cwd": self.cwd, "timeout": final_timeout}
            if cancel_token is not None:
                kwargs["cancel_token"] = cancel_token
            return_code, stdout, stderr = await run_subprocess(cmd, **kwargs)
        except asyncio.TimeoutError:
            logger.warning("JsonCliRunner: Command timed out: %s", " ".join(cmd))
            return CliResult(
                command=cmd,
                ok=False,
                return_code=-1, # Convention for timeout
                raw_stdout="",
                raw_stderr="Command timed out.",
                error_message="Command timed out.",
                timeout=final_timeout
            )
        except CancelledError as e:
            logger.warning("JsonCliRunner: Command cancelled: %s", " ".join(cmd))
            return CliResult(
                command=cmd,
                ok=False,
                return_code=-3,
                raw_stdout="",
                raw_stderr=str(e),
                error_message=f"Command cancelled: {e}",
                timeout=final_timeout,
            )
        except Exception as e:
            logger.exception("JsonCliRunner: Failed to run command: %s", " ".join(cmd))
            return CliResult(
                command=cmd,
                ok=False,
                return_code=-2, # Convention for execution error
                raw_stdout="",
                raw_stderr=str(e),
                error_message=f"Failed to execute command: {e}"
            )

        parsed_json = None
        error_message = None
        ok = (return_code == 0)

        if ok:
            try:
                parsed_json = json.loads(stdout)
            except json.JSONDecodeError:
                ok = False
                error_message = "Stdout is not valid JSON."
                logger.warning("JsonCliRunner: Stdout not JSON for command %s: %s", " ".join(cmd), stdout)
        else:
            error_message = f"Command exited with non-zero code {return_code}. Stderr: {stderr}"
            logger.warning("JsonCliRunner: Command failed %s: %s", " ".join(cmd), error_message)

        return CliResult(
            command=cmd,
            ok=ok,
            return_code=return_code,
            raw_stdout=stdout,
            raw_stderr=stderr,
            parsed_json=parsed_json,
            error_message=error_message,
        )
