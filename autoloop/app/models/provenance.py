from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ProvenanceRelation(str, Enum):
    DERIVED_FROM = "derived_from"
    VALIDATED_BY = "validated_by"
    MODIFIED_BY = "modified_by"
    FAILED_BY = "failed_by"
    REPAIRED_BY = "repaired_by"


class ArtifactRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    artifact_id: str = Field(min_length=1)
    artifact_type: str = Field(min_length=1)
    path: str | None = None
    module_id: str | None = None


class ProvenanceEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    phase_id: str = Field(min_length=1)
    artifact_id: str = Field(min_length=1)
    event_type: str = Field(min_length=1)
    timestamp: datetime = Field(default_factory=datetime.now)
    payload: dict[str, Any] = Field(default_factory=dict)


class ProvenanceEdge(BaseModel):
    model_config = ConfigDict(extra="forbid")

    src_artifact_id: str = Field(min_length=1)
    dst_artifact_id: str = Field(min_length=1)
    relation: ProvenanceRelation

