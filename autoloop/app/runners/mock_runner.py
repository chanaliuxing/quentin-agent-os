import asyncio
import json
from datetime import datetime
from pathlib import Path

from app.models import AgentStatus, AgentRole
from app.config import settings
from app.utils import get_contract_file
from .base import BaseAgentRunner, AgentRunContext, AgentRunResult


class MockRunner(BaseAgentRunner):
    async def run(self, context: AgentRunContext) -> AgentRunResult:
        started_at = datetime.now()

        await asyncio.sleep(2)

        module_name = context.module_name or "module_main"
        if context.agent == AgentRole.PLANNER:
            result_content = json.dumps(
                {
                    "contract_version": "1.0",
                    "generated_at": datetime.now().isoformat(),
                    "module_name": module_name,
                    "plan_summary": f"Plan for {module_name}",
                    "tasks": [f"Implement {module_name}", f"Test {module_name}"],
                    "acceptance_criteria": [f"{module_name} unit tests pass"],
                },
                ensure_ascii=False,
            )
        elif context.agent == AgentRole.REVIEWER:
            result_content = json.dumps(
                {
                    "contract_version": "1.0",
                    "generated_at": datetime.now().isoformat(),
                    "module_name": module_name,
                    "verdict": "approved",
                    "findings": [],
                },
                ensure_ascii=False,
            )
        elif context.agent == AgentRole.QA:
            result_content = json.dumps(
                {
                    "contract_version": "1.0",
                    "generated_at": datetime.now().isoformat(),
                    "module_name": module_name,
                    "status": "pass",
                    "tests_run": 3,
                    "tests_passed": 3,
                    "tests_failed": 0,
                    "issues": [],
                },
                ensure_ascii=False,
            )
        else:
            result_content = json.dumps(
                {
                    "contract_version": "1.0",
                    "generated_at": datetime.now().isoformat(),
                    "module_name": module_name,
                    "status": "success",
                    "files_changed": [
                        f"app/{module_name}/mock_file_1.py",
                        f"app/{module_name}/mock_file_2.py",
                    ],
                    "implementation_notes": f"Mock work completed by {context.agent.value}",
                },
                ensure_ascii=False,
            )

        context.result_file.parent.mkdir(parents=True, exist_ok=True)
        context.result_file.write_text(result_content)
        if context.agent in {AgentRole.DEV, AgentRole.QA}:
            self._materialize_required_artifacts(
                phase_id=context.phase_id,
                module_name=module_name,
                working_dir=context.working_dir,
            )

        hook_file = settings.hooks_dir / f"{context.phase_id}_{context.agent.value}_done.json"
        hook_file.parent.mkdir(parents=True, exist_ok=True)
        hook_file.write_text(
            f'{{"agent": "{context.agent.value}", "phase": "{context.phase_id}", "status": "success"}}'
        )

        completed_at = datetime.now()
        duration = (completed_at - started_at).total_seconds()

        return AgentRunResult(
            status=AgentStatus.SUCCESS,
            exit_code=0,
            stdout=f"Mock {context.agent.value} completed successfully",
            stderr="",
            duration_seconds=duration,
            commit_sha="mock_commit_sha_" + context.agent.value,
            started_at=started_at,
            completed_at=completed_at,
        )

    async def health_check(self) -> bool:
        return True

    def _materialize_required_artifacts(
        self,
        *,
        phase_id: str,
        module_name: str,
        working_dir: Path,
    ) -> None:
        spec_file = get_contract_file(phase_id, module_name, "acceptance_spec")
        if not spec_file.exists():
            return
        try:
            payload = json.loads(spec_file.read_text(encoding="utf-8"))
        except Exception:
            return
        required_artifacts = payload.get("required_artifacts", [])
        if not isinstance(required_artifacts, list):
            return
        artifact_payload = {"status": "ok", "phase_id": phase_id, "module_name": module_name}
        for artifact in required_artifacts:
            artifact_text = str(artifact).strip()
            if not artifact_text:
                continue
            candidate = Path(artifact_text)
            artifact_file = candidate if candidate.is_absolute() else (working_dir / candidate)
            artifact_file.parent.mkdir(parents=True, exist_ok=True)
            if artifact_file.suffix == ".json":
                artifact_file.write_text(json.dumps(artifact_payload, ensure_ascii=False, indent=2), encoding="utf-8")
            else:
                artifact_file.write_text("mock artifact\n", encoding="utf-8")
