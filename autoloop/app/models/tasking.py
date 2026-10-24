from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


class TaskPacket(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    phase_id: str = Field(min_length=1)
    module_id: str = Field(min_length=1)
    agent: str = Field(min_length=1)
    sor_refs: list[str] = Field(default_factory=list)
    input_artifact_ids: list[str] = Field(default_factory=list)
    writable_paths: list[str] = Field(default_factory=list, min_length=1)
    expected_output_contract: str = Field(min_length=1)
    gate_expectations: list[str] = Field(default_factory=list)


class ResultPacket(BaseModel):
    model_config = ConfigDict(extra="forbid")

    result_id: str = Field(min_length=1)
    task_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    phase_id: str = Field(min_length=1)
    module_id: str = Field(min_length=1)
    agent: str = Field(min_length=1)
    produced_artifact_ids: list[str] = Field(default_factory=list)
    contract_payload: dict[str, Any] = Field(default_factory=dict)
    claimed_file_changes: list[str] = Field(default_factory=list)


class PromptPacket(BaseModel):
    model_config = ConfigDict(extra="forbid")

    prompt_id: str = Field(min_length=1)
    task_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    phase_id: str = Field(min_length=1)
    module_id: str = Field(min_length=1)
    agent: str = Field(min_length=1)
    system_prompt: str = Field(min_length=1)
    user_prompt: str = Field(min_length=1)
    rendered_task_markdown: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_prompt_identity(self) -> "PromptPacket":
        if not self.task_id.startswith("task_") and not self.task_id:
            raise ValueError("task_id must be present")
        return self
