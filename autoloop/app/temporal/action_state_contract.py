from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class ActionStateContract(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action_id: str = Field(min_length=1)
    pre_state: dict[str, object] = Field(default_factory=dict)
    expected_state_delta: dict[str, object] = Field(default_factory=dict)
    verify_rule: str = Field(min_length=1)
    rollback_hook: str = Field(min_length=1)
    observed_state: dict[str, object] = Field(default_factory=dict)
    verified: bool = False
