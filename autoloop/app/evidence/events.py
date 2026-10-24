from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from app.config import settings


class EventRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_id: str = Field(min_length=1)
    event_time: str = Field(min_length=1)
    workflow_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    phase_id: str = Field(min_length=1)
    stage: str = Field(min_length=1)
    actor: str = Field(min_length=1)
    event_type: str = Field(min_length=1)
    attempt: int = 1
    cause_class: str = ""
    failure_type: str | None = None
    payload: dict = Field(default_factory=dict)
    artifact_refs: list[str] = Field(default_factory=list)
    trace_id: str | None = None
    parent_event_id: str | None = None
    supersedes_event_id: str | None = None
    created_at: datetime = Field(default_factory=datetime.now)


class EventStore:
    def __init__(self, base_dir: Path | None = None) -> None:
        self.base_dir = base_dir or (settings.runtime_dir / "event_log")

    def append(self, event: EventRecord) -> Path:
        run_dir = self.base_dir / event.workflow_id / event.phase_id
        run_dir.mkdir(parents=True, exist_ok=True)
        path = run_dir / "events.jsonl"
        with path.open("a", encoding="utf-8") as file:
            file.write(event.model_dump_json())
            file.write("\n")
        return path

    def read(self, workflow_id: str, phase_id: str) -> list[dict]:
        path = self.base_dir / workflow_id / phase_id / "events.jsonl"
        if not path.exists():
            return []
        events: list[dict] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                events.append(json.loads(line))
            except Exception:
                continue
        return events
