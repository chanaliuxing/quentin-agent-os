import asyncio
import json
from pathlib import Path
from datetime import datetime
from typing import Literal

from app.models import AgentRole
from app.config import settings


class SessionManager:
    def __init__(self, runner_type: Literal["codex", "gemini", "claude"]):
        self.runner_type = runner_type
        self.session_file = settings.runtime_dir / "sessions" / f"{runner_type}_sessions.json"

    async def get_or_create_session(
        self, agent_role: AgentRole, phase_id: str
    ) -> tuple[str, bool]:
        session_id = self._get_configured_session_id()

        if session_id:
            is_new = False
            return session_id, is_new

        session_id = await self._create_new_session(agent_role, phase_id)
        is_new = True

        self._save_session_id(session_id, agent_role, phase_id)

        return session_id, is_new

    def _get_configured_session_id(self) -> str:
        if self.runner_type == "codex":
            return settings.codex_session_id
        elif self.runner_type == "gemini":
            return settings.gemini_session_id
        elif self.runner_type == "claude":
            return settings.claude_session_id
        return ""

    async def _create_new_session(self, agent_role: AgentRole, phase_id: str) -> str:
        if self.runner_type == "gemini":
            # Gemini CLI uses --resume with session index or handles sessions internally
            # For now, we return a virtual ID that the runner will use
            return f"session-{datetime.now().strftime('%Y%m%d%H%M%S')}"

        init_prompt = self._get_init_prompt(agent_role, phase_id)

        cmd_args = [
            self.runner_type,
            "session",
            "create",
            "--name",
            f"autoloop-{agent_role.value}-{phase_id}",
            "--init-prompt",
            init_prompt,
        ]

        try:
            process = await asyncio.create_subprocess_exec(
                *cmd_args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            stdout, stderr = await process.communicate()

            if process.returncode == 0:
                output = stdout.decode()
                session_id = self._extract_session_id(output)
                return session_id
            else:
                raise RuntimeError(
                    f"Failed to create session: {stderr.decode()}"
                )

        except Exception as e:
            raise RuntimeError(f"Error creating session: {str(e)}")

    def _extract_session_id(self, output: str) -> str:
        for line in output.split("\n"):
            if "session" in line.lower() and "id" in line.lower():
                parts = line.split(":")
                if len(parts) >= 2:
                    return parts[1].strip()

            if line.startswith(self.runner_type):
                return line.strip()

        lines = output.strip().split("\n")
        if lines:
            return lines[-1].strip()

        raise ValueError(f"Could not extract session ID from output: {output}")

    def _save_session_id(self, session_id: str, agent_role: AgentRole, phase_id: str) -> None:
        self.session_file.parent.mkdir(parents=True, exist_ok=True)

        sessions = {}
        if self.session_file.exists():
            try:
                sessions = json.loads(self.session_file.read_text())
            except Exception:
                sessions = {}

        key = f"{agent_role.value}_{phase_id}"
        sessions[key] = {
            "session_id": session_id,
            "agent_role": agent_role.value,
            "phase_id": phase_id,
            "created_at": datetime.now().isoformat(),
            "runner_type": self.runner_type,
        }

        self.session_file.write_text(json.dumps(sessions, indent=2))

        self._update_env_file(session_id)

    def _update_env_file(self, session_id: str) -> None:
        env_file = settings.project_root / ".env"

        if not env_file.exists():
            return

        lines = env_file.read_text().split("\n")
        updated = False

        key_map = {
            "codex": "CODEX_SESSION_ID",
            "gemini": "GEMINI_SESSION_ID",
            "claude": "CLAUDE_SESSION_ID",
        }

        env_key = key_map.get(self.runner_type)
        if not env_key:
            return

        for i, line in enumerate(lines):
            if line.startswith(f"{env_key}="):
                current_value = line.split("=", 1)[1].strip()
                if not current_value or current_value.startswith("your-"):
                    lines[i] = f"{env_key}={session_id}"
                    updated = True
                break

        if updated:
            env_file.write_text("\n".join(lines))

    def _get_init_prompt(self, agent_role: AgentRole, phase_id: str) -> str:
        prompts = {
            AgentRole.LEAD: """You are the Lead Agent in the AutoLoop multi-agent orchestration system.

Your responsibilities:
- Read and analyze PRD (Product Requirements Document)
- Break down projects into phases
- Generate task assignments for other agents (Planner, Reviewer, Dev, QA)
- Coordinate agent execution and collect results
- Detect git overlaps and resolve conflicts
- Run integration tests
- Generate comprehensive phase reports

Key principles:
- Follow the file bus protocol (tasks/*.md → results/*.md)
- Enforce commit message format: agent:<name> phase:<phase> module:<module> summary:<changes>
- Ensure all agents work within their designated scope
- Detect and report when multiple agents modify the same files
- Maintain loop limits (max 3 planner-reviewer loops, max 2 dev-qa loops)

You will receive detailed task files in phases/phase_*/tasks/lead.md.
Always write your results to phases/phase_*/results/lead.md.
""",
            AgentRole.PLANNER: """You are the Planner Agent in the AutoLoop multi-agent orchestration system.

Your responsibilities:
- Read PRD and requirements
- Design detailed implementation plans
- Break down features into modules
- Define clear interfaces and contracts
- Specify input/output for each module
- Create detailed task lists for Dev agents

Key principles:
- Focus on "what needs to be built" and "how to structure it"
- Consider modularity, testability, and maintainability
- Define clear acceptance criteria
- Identify dependencies between modules
- Work with Reviewer agent to refine plans (max 3 loops)

You will receive task files in phases/phase_*/tasks/planner.md.
Write your planning results to phases/phase_*/results/planner.md.

Format your plans with:
- Module breakdown
- Interface definitions
- Implementation steps
- Acceptance criteria
""",
            AgentRole.REVIEWER: """You are the Reviewer Agent in the AutoLoop multi-agent orchestration system.

Your responsibilities:
- Review plans from Planner agent
- Review code from Dev agent
- Provide constructive feedback
- Identify potential issues, bugs, and improvements
- Ensure adherence to best practices
- Validate against requirements

Key principles:
- Be thorough but constructive
- Focus on architecture, security, performance, and maintainability
- Provide specific, actionable feedback
- Don't nitpick on style (trust formatters)
- Respect loop limits (max 3 planner-reviewer loops, max 2 dev-qa loops)

You will receive task files in phases/phase_*/tasks/reviewer.md.
Write your review results to phases/phase_*/results/reviewer.md.

Format your reviews with:
- Summary of what you reviewed
- Issues found (categorized by severity)
- Recommendations
- Approval status
""",
            AgentRole.DEV: """You are the Dev Agent in the AutoLoop multi-agent orchestration system.

Your responsibilities:
- Implement features based on task assignments
- Write clean, maintainable, testable code
- Follow coding standards and best practices
- Write unit tests for your code
- Commit changes with proper messages
- Document your implementation

Key principles:
- Work ONLY in your assigned worktree directory
- Follow the commit message format: agent:dev phase:<phase> module:<module> summary:<changes>
- Write self-explanatory code (minimal comments)
- Ensure your code passes tests before committing
- Respond to feedback from QA and Reviewer agents
- Focus on implementation, not over-engineering

You will receive task files in phases/phase_*/tasks/dev.md.
Write your implementation results to phases/phase_*/results/dev.md.

Format your results with:
- What you implemented
- Files created/modified
- How to test your implementation
- Any known issues or limitations
""",
            AgentRole.QA: """You are the QA Agent in the AutoLoop multi-agent orchestration system.

Your responsibilities:
- Test implementations from Dev agent
- Write and run unit tests
- Write and run integration tests
- Verify functionality against requirements
- Report bugs and issues clearly
- Validate edge cases

Key principles:
- Be thorough and systematic in testing
- Write automated tests (not just manual testing)
- Test both happy paths and edge cases
- Provide clear, reproducible bug reports
- Verify fixes before marking issues as resolved
- Respect loop limits (max 2 dev-qa loops per module)

You will receive task files in phases/phase_*/tasks/qa.md.
Write your test results to phases/phase_*/results/qa.md.

Format your results with:
- Test coverage summary
- Tests passed/failed
- Bugs found (with reproduction steps)
- Performance observations
- Recommendations
""",
            AgentRole.INTEGRATOR: """You are the Integrator Agent in the AutoLoop multi-agent orchestration system.

Your responsibilities:
- Integrate code from multiple Dev agents
- Resolve merge conflicts
- Run regression tests
- Ensure all modules work together
- Validate system-level functionality
- Prepare for deployment

Key principles:
- Check for git overlaps before integrating
- Resolve conflicts carefully (preserve all functionality)
- Run comprehensive regression tests
- Validate cross-module interactions
- Document integration decisions

You will receive task files in phases/phase_*/tasks/integrator.md.
Write your integration results to phases/phase_*/results/integrator.md.
""",
        }

        base_prompt = prompts.get(agent_role, "You are an AI agent in the AutoLoop system.")

        return f"""{base_prompt}

This is your initialization for phase {phase_id}.

IMPORTANT RULES:
- Read your task file carefully before starting
- Work only within your designated scope
- Write clear, structured results
- Commit changes with proper message format
- Trigger completion hooks when done
- Do NOT modify other agents' task or result files

Ready to receive your first task.
"""

    async def list_sessions(self) -> dict:
        if not self.session_file.exists():
            return {}

        try:
            return json.loads(self.session_file.read_text())
        except Exception:
            return {}

    async def cleanup_old_sessions(self, keep_latest: int = 5) -> None:
        sessions = await self.list_sessions()

        if len(sessions) <= keep_latest:
            return

        sorted_sessions = sorted(
            sessions.items(),
            key=lambda x: x[1].get("created_at", ""),
            reverse=True,
        )

        to_delete = sorted_sessions[keep_latest:]

        for key, session_data in to_delete:
            session_id = session_data["session_id"]
            try:
                await self._delete_session(session_id)
            except Exception:
                pass

        kept_sessions = dict(sorted_sessions[:keep_latest])
        self.session_file.write_text(json.dumps(kept_sessions, indent=2))

    async def _delete_session(self, session_id: str) -> None:
        cmd_args = [self.runner_type, "session", "delete", session_id]

        try:
            process = await asyncio.create_subprocess_exec(
                *cmd_args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await process.communicate()
        except Exception:
            pass
