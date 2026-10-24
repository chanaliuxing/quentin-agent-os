from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Literal
from datetime import datetime
from pydantic import BaseModel, Field

from app.models import AgentRole, AgentStatus, default_contract_template
from app.observability.metrics import MetricsCollector, MetricsTimer, classify_error


class AgentRunContext(BaseModel):
    agent: AgentRole
    project_id: str = "autoloop-project"
    module_name: str | None = None
    task_file: Path
    result_file: Path
    working_dir: Path
    worktree_id: str = ""
    log_file: Path
    phase_id: str
    timeout_seconds: int = 1800
    env_vars: dict[str, str] = Field(default_factory=dict)


class AgentRunResult(BaseModel):
    status: AgentStatus
    exit_code: int = 0
    stdout: str = ""
    stderr: str = ""
    duration_seconds: float = 0.0
    commit_sha: str | None = None
    error_message: str | None = None
    artifacts: dict[str, Any] = Field(default_factory=dict)
    started_at: datetime = Field(default_factory=datetime.now)
    completed_at: datetime = Field(default_factory=datetime.now)


class BaseAgentRunner(ABC):
    def __init__(self, config: dict[str, Any] | None = None):
        self.config = config or {}
        self.runner_type: Literal["codex", "gemini", "claude", "mock"] | None = None

    @abstractmethod
    async def run(self, context: AgentRunContext) -> AgentRunResult:
        pass

    @abstractmethod
    async def health_check(self) -> bool:
        pass

    async def ensure_session(self, agent_role: AgentRole, phase_id: str) -> tuple[str, bool]:
        if self.runner_type in ["codex", "gemini", "claude"]:
            from app.runners.session_manager import SessionManager

            manager = SessionManager(self.runner_type)
            return await manager.get_or_create_session(agent_role, phase_id)
        return "", False

    def _build_prompt(self, context: AgentRunContext) -> str:
        task_content = context.task_file.read_text() if context.task_file.exists() else ""
        contract_example = default_contract_template(context.agent, context.module_name)

        prompt = f"""You are {context.agent.value} agent in phase {context.phase_id}.

YOUR TASK (from {context.task_file}):
{task_content}

CONSTRAINTS:
- Work ONLY in directory: {context.working_dir}
- Write your result to: {context.result_file}
- Do NOT scan or modify tasks for other agents
- Output MUST be valid JSON only (no markdown)
- JSON MUST match the output contract schema for your role
- Do NOT run git commit or git push (lead integrator handles repository history)

After completing your task:
1. Write JSON output to result file matching this schema example:
{contract_example}
2. Exit

Begin now.
"""
        return prompt
