import asyncio
from pathlib import Path
from datetime import datetime

from app.models import AgentStatus
from app.utils.process import run_subprocess_with_timeout
from app.observability.metrics import MetricsCollector, MetricsTimer, classify_error
from .base import BaseAgentRunner, AgentRunContext, AgentRunResult


class GeminiRunner(BaseAgentRunner):
    def __init__(self, config: dict | None = None):
        super().__init__(config)
        self.runner_type = "gemini"
        self.session_id = self.config.get("session_id", "")

    async def run(self, context: AgentRunContext) -> AgentRunResult:
        started_at = datetime.now()

        from .session_manager import SessionManager
        manager = SessionManager("gemini")
        init_prompt = manager._get_init_prompt(context.agent, context.phase_id)
        task_prompt = self._build_prompt(context)
        full_prompt = f"{init_prompt}\n\nYOUR CURRENT TASK:\n{task_prompt}"

        cmd_args = [
            "gemini",
            "--yolo",
            "-p",
            "",
        ]

        try:
            with MetricsTimer() as timer:
                result = await run_subprocess_with_timeout(
                    cmd=cmd_args,
                    cwd=str(context.working_dir),
                    timeout=context.timeout_seconds,
                    log_file=context.log_file,
                    env=context.env_vars,
                    stdin_input=full_prompt,
                )

            MetricsCollector.record_cli_call(
                cli_type="gemini",
                agent_role=context.agent.value,
                duration_seconds=timer.duration_seconds,
            )

            completed_at = datetime.now()
            duration = (completed_at - started_at).total_seconds()

            if result["returncode"] == 0:
                status = AgentStatus.SUCCESS
                error_message = None
            else:
                status = AgentStatus.FAILED
                error_message = f"Exit code {result['returncode']}: {result['stderr'][:500]}"
                MetricsCollector.increment_cli_errors("gemini", "execution_error")

            commit_sha = await self._get_latest_commit(context.working_dir)

            return AgentRunResult(
                status=status,
                exit_code=result["returncode"],
                stdout=result["stdout"],
                stderr=result["stderr"],
                duration_seconds=duration,
                commit_sha=commit_sha,
                error_message=error_message,
                started_at=started_at,
                completed_at=completed_at,
            )

        except asyncio.TimeoutError:
            MetricsCollector.increment_cli_errors("gemini", "timeout")
            completed_at = datetime.now()
            duration = (completed_at - started_at).total_seconds()
            return AgentRunResult(
                status=AgentStatus.FAILED,
                exit_code=-1,
                error_message=f"Timeout after {context.timeout_seconds}s",
                duration_seconds=duration,
                started_at=started_at,
                completed_at=completed_at,
            )

        except Exception as e:
            error_type = classify_error(e)
            MetricsCollector.increment_cli_errors("gemini", error_type)
            completed_at = datetime.now()
            duration = (completed_at - started_at).total_seconds()
            return AgentRunResult(
                status=AgentStatus.FAILED,
                exit_code=-1,
                error_message=f"Exception: {str(e)}",
                duration_seconds=duration,
                started_at=started_at,
                completed_at=completed_at,
            )

    async def health_check(self) -> bool:
        try:
            result = await asyncio.create_subprocess_exec(
                "gemini",
                "--version",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await result.communicate()
            return result.returncode == 0
        except Exception:
            return False

    async def _get_latest_commit(self, working_dir: Path) -> str | None:
        try:
            result = await asyncio.create_subprocess_exec(
                "git",
                "rev-parse",
                "HEAD",
                cwd=str(working_dir),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await result.communicate()
            if result.returncode == 0:
                return stdout.decode().strip()
        except Exception:
            pass
        return None
