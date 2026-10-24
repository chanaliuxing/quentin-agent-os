import asyncio
from pathlib import Path
from datetime import datetime

from app.config import settings
from app.models import AgentRole, AgentStatus
from app.metrics import bump_runner_health
from app.utils.process import run_subprocess_with_timeout
from app.observability.metrics import MetricsCollector, MetricsTimer, classify_error
from .session_policy import get_agent_specs, resolve_codex_session
from .base import BaseAgentRunner, AgentRunContext, AgentRunResult


class CodexRunner(BaseAgentRunner):
    _resume_health_cache: dict[str, dict] = {}

    def __init__(self, config: dict | None = None):
        super().__init__(config)
        self.runner_type = "codex"
        raw_session_id = str(self.config.get("session_id", "")).strip()
        placeholder_tokens = ("your-", "<", ">", "session-id", "session_id")
        if raw_session_id and any(token in raw_session_id.lower() for token in placeholder_tokens):
            raw_session_id = ""
        self.session_id = raw_session_id
        self.degraded_keywords = (
            "failed to open state db",
            "migration 19 was previously applied but is missing",
            "database disk image is malformed",
            "unable to open database file",
            "state db corrupted",
        )
        self.usage_limit_keywords = (
            "hit your usage limit",
            "usage limit",
            "rate limit",
            "quota",
            "429",
            "too many requests",
        )
        self.planner_os_env_panic_keywords = (
            "operation not permitted (os error 1)",
            "failed to install system skills",
            "reqwest-internal-sync-runtime",
            "system-configuration-0.6.1/src/dynamic_store.rs",
        )

    async def run(self, context: AgentRunContext) -> AgentRunResult:
        started_at = datetime.now()

        prompt = self._build_prompt(context)
        role_key = str(context.agent.value).strip().lower()
        specs = get_agent_specs()
        spec = specs.get(role_key)
        spec_session_id = str(getattr(spec, "session_id", "") or "").strip()
        env_session_id = str((context.env_vars or {}).get("CODEX_SESSION_ID", "")).strip()
        explicit_source = "agent_spec" if spec_session_id else "env"
        session_resolution = resolve_codex_session(
            role=role_key,
            project_id=str(context.project_id or "autoloop-project"),
            worktree_id=str(context.worktree_id or context.working_dir),
            explicit_session_id=spec_session_id or env_session_id,
            explicit_source=explicit_source,
            global_fallback_session_id=(self.session_id or "").strip(),
        )
        session_id = str(session_resolution.session_id or "").strip()
        mode_chain = await self._build_mode_chain(prompt=prompt, session_id=session_id, context=context)

        try:
            result: dict | None = None
            selected_mode = ""
            last_error_message = ""
            attempt_timeout = min(context.timeout_seconds, max(1, settings.codex_attempt_timeout_seconds))
            with MetricsTimer() as timer:
                for mode_name, cmd_args in mode_chain:
                    current_result = await run_subprocess_with_timeout(
                        cmd=cmd_args,
                        cwd=str(context.working_dir),
                        timeout=attempt_timeout,
                        log_file=context.log_file,
                        env=context.env_vars,
                    )
                    stderr_text = str(current_result.get("stderr", ""))
                    stdout_text = str(current_result.get("stdout", ""))
                    usage_limited = self._contains_usage_limit_signal(stderr_text) or self._contains_usage_limit_signal(
                        stdout_text
                    )
                    if usage_limited:
                        bump_runner_health("usage_limit_count")
                        result = current_result
                        selected_mode = mode_name
                        break
                    degraded = self._contains_degraded_signal(stderr_text)
                    if degraded and mode_name != "ephemeral":
                        bump_runner_health("state_db_fallback_count")
                        bump_runner_health("session_degraded_count")
                        last_error_message = "codex_state_db_degraded"
                        continue
                    planner_os_env_panic = self._should_fallback_for_planner_os_env_panic(
                        context=context,
                        mode_name=mode_name,
                        stdout_text=stdout_text,
                        stderr_text=stderr_text,
                    )
                    if planner_os_env_panic:
                        bump_runner_health("session_degraded_count")
                        last_error_message = "codex_planner_os_env_panic"
                        continue
                    result = current_result
                    selected_mode = mode_name
                    break

            completed_at = datetime.now()
            duration = (completed_at - started_at).total_seconds()
            if result is None:
                result = {"returncode": 1, "stdout": "", "stderr": last_error_message}
                selected_mode = "exhausted"

            MetricsCollector.record_cli_call(
                cli_type="codex",
                agent_role=context.agent.value,
                duration_seconds=timer.duration_seconds,
            )

            if result["returncode"] == 0:
                status = AgentStatus.SUCCESS
                error_message = None
            else:
                status = AgentStatus.FAILED
                error_message = f"Exit code {result['returncode']}: {result['stderr'][:500]}"
                MetricsCollector.increment_cli_errors("codex", "execution_error")
            error_class = self._classify_error_class(stdout=str(result.get("stdout", "")), stderr=str(result.get("stderr", "")))

            commit_sha = await self._get_latest_commit(context.working_dir)

            return AgentRunResult(
                status=status,
                exit_code=result["returncode"],
                stdout=result["stdout"],
                stderr=result["stderr"],
                duration_seconds=duration,
                commit_sha=commit_sha,
                error_message=error_message,
                artifacts={
                    "execution_mode": selected_mode,
                    "error_class": error_class,
                    "session_source": session_resolution.source,
                    "session_scope": str(session_resolution.scope),
                    "session_policy_key": session_resolution.policy_key,
                    "session_role": session_resolution.role,
                },
                started_at=started_at,
                completed_at=completed_at,
            )

        except asyncio.TimeoutError:
            MetricsCollector.increment_cli_errors("codex", "timeout")
            bump_runner_health("execution_timeout_count")
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
            MetricsCollector.increment_cli_errors("codex", error_type)
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

    async def _build_mode_chain(
        self,
        *,
        prompt: str,
        session_id: str,
        context: AgentRunContext,
    ) -> list[tuple[str, list[str]]]:
        mode_chain: list[tuple[str, list[str]]] = []
        if settings.codex_prefer_ephemeral and settings.codex_ephemeral_fallback_enabled:
            mode_chain.append(
                (
                    "ephemeral",
                    [
                        "codex",
                        "exec",
                        prompt,
                        "--json",
                        "--full-auto",
                        "--skip-git-repo-check",
                        "--ephemeral",
                    ],
                )
            )
            mode_chain.append(
                (
                    "standard",
                    [
                        "codex",
                        "exec",
                        prompt,
                        "--json",
                        "--full-auto",
                        "--skip-git-repo-check",
                    ],
                )
            )
            return mode_chain

        degraded = await self._probe_state_db(context=context)
        resume_health = await self._resume_health_check(session_id=session_id, context=context)
        if settings.codex_resume_enabled and session_id and not degraded and bool(resume_health.get("healthy")):
            mode_chain.append(
                (
                    "resume",
                    [
                        "codex",
                        "exec",
                        "resume",
                        session_id,
                        prompt,
                        "--json",
                        "--full-auto",
                        "--skip-git-repo-check",
                    ],
                )
            )
        mode_chain.append(
            (
                "standard",
                [
                    "codex",
                    "exec",
                    prompt,
                    "--json",
                    "--full-auto",
                    "--skip-git-repo-check",
                ],
            )
        )
        if settings.codex_ephemeral_fallback_enabled and not settings.codex_prefer_ephemeral:
            mode_chain.append(
                (
                    "ephemeral",
                    [
                        "codex",
                        "exec",
                        prompt,
                        "--json",
                        "--full-auto",
                        "--skip-git-repo-check",
                        "--ephemeral",
                    ],
                )
            )
        return mode_chain

    def _should_fallback_for_planner_os_env_panic(
        self,
        *,
        context: AgentRunContext,
        mode_name: str,
        stdout_text: str,
        stderr_text: str,
    ) -> bool:
        if context.agent != AgentRole.PLANNER:
            return False
        if mode_name == "ephemeral":
            return False
        combined = f"{stdout_text}\n{stderr_text}".lower()
        matches = sum(1 for keyword in self.planner_os_env_panic_keywords if keyword in combined)
        return matches >= 2

    async def _resume_health_check(self, *, session_id: str, context: AgentRunContext) -> dict:
        session_id = str(session_id).strip()
        if not session_id:
            return {"healthy": False, "reason": "missing_session_id"}
        cached = self._resume_health_cache.get(session_id)
        if cached is not None:
            return dict(cached)

        rollout_path = self._find_rollout_path(session_id)
        if rollout_path is None:
            result = {"healthy": False, "reason": "rollout_missing"}
            self._resume_health_cache[session_id] = result
            return dict(result)

        probe_log = context.log_file.parent / f"{context.phase_id}_{context.agent.value}_resume_probe.log"
        probe_cmd = [
            "codex",
            "exec",
            "resume",
            session_id,
            "Output EXACTLY READY and exit.",
            "--json",
            "--skip-git-repo-check",
            "--full-auto",
        ]
        try:
            result = await run_subprocess_with_timeout(
                cmd=probe_cmd,
                cwd=str(context.working_dir),
                timeout=settings.codex_resume_probe_timeout_seconds,
                log_file=probe_log,
                env=context.env_vars,
            )
        except Exception:
            bump_runner_health("probe_failure_count")
            snapshot = {
                "healthy": True,
                "reason": "resume_probe_exception_nonblocking",
                "rollout_path": str(rollout_path),
            }
            self._resume_health_cache[session_id] = snapshot
            return dict(snapshot)

        stderr_text = str(result.get("stderr", ""))
        stdout_text = str(result.get("stdout", ""))
        if self._contains_usage_limit_signal(stderr_text) or self._contains_usage_limit_signal(stdout_text):
            bump_runner_health("usage_limit_count")
            snapshot = {
                "healthy": True,
                "reason": "resume_probe_usage_limited_nonblocking",
                "rollout_path": str(rollout_path),
            }
            self._resume_health_cache[session_id] = snapshot
            return dict(snapshot)
        if self._contains_degraded_signal(stderr_text):
            bump_runner_health("state_db_fallback_count")
            bump_runner_health("session_degraded_count")
            snapshot = {"healthy": False, "reason": "state_db_degraded", "rollout_path": str(rollout_path)}
            self._resume_health_cache[session_id] = snapshot
            return dict(snapshot)
        if int(result.get("returncode", 1)) != 0:
            snapshot = {
                "healthy": False,
                "reason": "resume_probe_failed",
                "rollout_path": str(rollout_path),
            }
            self._resume_health_cache[session_id] = snapshot
            return dict(snapshot)

        model_mismatch = "recorded with model" in stdout_text.lower() or "recorded with model" in stderr_text.lower()
        snapshot = {
            "healthy": True,
            "reason": "ok",
            "rollout_path": str(rollout_path),
            "model_mismatch": model_mismatch,
        }
        self._resume_health_cache[session_id] = snapshot
        return dict(snapshot)

    def _find_rollout_path(self, session_id: str) -> Path | None:
        sessions_root = Path.home() / ".codex" / "sessions"
        if not sessions_root.exists():
            return None
        matches = sorted(sessions_root.rglob(f"*{session_id}.jsonl"))
        if not matches:
            return None
        return matches[-1]

    async def _probe_state_db(self, *, context: AgentRunContext) -> bool:
        if not settings.codex_probe_enabled:
            return False
        probe_log = context.log_file.parent / f"{context.phase_id}_{context.agent.value}_probe.log"
        probe_cmd = [
            "codex",
            "exec",
            "Output EXACTLY READY and exit.",
            "--json",
            "--skip-git-repo-check",
        ]
        try:
            result = await run_subprocess_with_timeout(
                cmd=probe_cmd,
                cwd=str(context.working_dir),
                timeout=settings.codex_probe_timeout_seconds,
                log_file=probe_log,
                env=context.env_vars,
            )
        except Exception:
            bump_runner_health("probe_failure_count")
            return False
        if self._contains_degraded_signal(str(result.get("stderr", ""))):
            bump_runner_health("state_db_fallback_count")
            return True
        return False

    def _contains_degraded_signal(self, text: str) -> bool:
        lowered = text.lower()
        return any(token in lowered for token in self.degraded_keywords)

    def _contains_usage_limit_signal(self, text: str) -> bool:
        lowered = text.lower()
        return any(token in lowered for token in self.usage_limit_keywords)

    def _classify_error_class(self, *, stdout: str, stderr: str) -> str:
        if self._contains_usage_limit_signal(stderr) or self._contains_usage_limit_signal(stdout):
            return "usage_limit"
        if self._contains_degraded_signal(stderr):
            return "state_db_degraded"
        return "generic"

    async def health_check(self) -> bool:
        try:
            result = await asyncio.create_subprocess_exec(
                "codex",
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
