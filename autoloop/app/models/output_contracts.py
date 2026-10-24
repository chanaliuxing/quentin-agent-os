import json
import re
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.state import AgentRole


class BaseContract(BaseModel):
    model_config = ConfigDict(extra="forbid")
    contract_version: Literal["1.0"] = "1.0"
    generated_at: datetime = Field(default_factory=datetime.now)
    constraints_ack: bool | None = None


class PlannerContract(BaseContract):
    module_name: str
    plan_summary: str
    tasks: list[str]
    acceptance_criteria: list[str]


class ReviewerContract(BaseContract):
    module_name: str
    verdict: Literal["approved", "needs_revision"]
    findings: list[str]
    finding_codes: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_finding_codes_for_revision(self) -> "ReviewerContract":
        if self.verdict == "needs_revision" and not self.finding_codes:
            raise ValueError("finding_codes is required when verdict=needs_revision")
        return self


class DevContract(BaseContract):
    module_name: str
    status: Literal["success", "failed"]
    files_changed: list[str]
    implementation_notes: str


class QAContract(BaseContract):
    module_name: str
    status: Literal["pass", "fail"]
    tests_run: int
    tests_passed: int
    tests_failed: int
    issues: list[str] = Field(default_factory=list)


CONTRACT_BY_ROLE: dict[AgentRole, type[BaseContract]] = {
    AgentRole.PLANNER: PlannerContract,
    AgentRole.REVIEWER: ReviewerContract,
    AgentRole.DEV: DevContract,
    AgentRole.QA: QAContract,
}


def extract_json_payload(text: str) -> dict[str, Any]:
    stripped = text.strip()
    if stripped.startswith("{") and stripped.endswith("}"):
        return json.loads(stripped)

    matches = re.findall(r"```json\s*(\{.*?\})\s*```", text, flags=re.DOTALL)
    if matches:
        return json.loads(matches[-1])

    first = text.find("{")
    last = text.rfind("}")
    if first != -1 and last != -1 and last > first:
        return json.loads(text[first : last + 1])

    raise ValueError("No JSON payload found in output")


def validate_output_contract(agent_role: AgentRole, text: str) -> BaseContract:
    if agent_role not in CONTRACT_BY_ROLE:
        raise ValueError(f"No output contract defined for role: {agent_role.value}")
    payload = extract_json_payload(text)
    model = CONTRACT_BY_ROLE[agent_role]
    return model.model_validate(payload)


def default_contract_template(agent_role: AgentRole, module_name: str | None) -> str:
    module = module_name or "module_main"
    if agent_role == AgentRole.DEV:
        return json.dumps(
            {
                "contract_version": "1.0",
                "generated_at": datetime.now().isoformat(),
                "constraints_ack": True,
                "module_name": module,
                "status": "success",
                "files_changed": ["path/to/file.py"],
                "implementation_notes": "Implementation summary.",
            },
            ensure_ascii=False,
            indent=2,
        )
    if agent_role == AgentRole.QA:
        return json.dumps(
            {
                "contract_version": "1.0",
                "generated_at": datetime.now().isoformat(),
                "constraints_ack": True,
                "module_name": module,
                "status": "pass",
                "tests_run": 1,
                "tests_passed": 1,
                "tests_failed": 0,
                "issues": [],
            },
            ensure_ascii=False,
            indent=2,
        )
    if agent_role == AgentRole.PLANNER:
        return json.dumps(
            {
                "contract_version": "1.0",
                "generated_at": datetime.now().isoformat(),
                "constraints_ack": True,
                "module_name": module,
                "plan_summary": "Plan summary.",
                "tasks": ["Task 1"],
                "acceptance_criteria": ["Criterion 1"],
            },
            ensure_ascii=False,
            indent=2,
        )
    if agent_role == AgentRole.REVIEWER:
        return json.dumps(
            {
                "contract_version": "1.0",
                "generated_at": datetime.now().isoformat(),
                "constraints_ack": True,
                "module_name": module,
                "verdict": "approved",
                "findings": [],
                "finding_codes": [],
            },
            ensure_ascii=False,
            indent=2,
        )
    raise ValueError(f"Unsupported role: {agent_role.value}")
