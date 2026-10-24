from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from app.config import settings


class EvidenceRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    record_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    phase_id: str = Field(min_length=1)
    workflow_version: str = Field(min_length=1)
    module_ids: list[str] = Field(default_factory=list)
    base_sha: str = ""
    head_sha: str = ""
    acceptance_status: str = Field(min_length=1)
    test_status: str = Field(min_length=1)
    missing_required_tests: list[str] = Field(default_factory=list)
    failed_required_tests: list[str] = Field(default_factory=list)
    required_test_outcomes: dict[str, str] = Field(default_factory=dict)
    required_test_failure_details: dict[str, list[str]] = Field(default_factory=dict)
    grader_results: dict[str, str] = Field(default_factory=dict)
    grader_details: dict[str, list[dict]] = Field(default_factory=dict)
    changed_files: list[str] = Field(default_factory=list)
    first_failure_stage: str = ""
    failure_type: str = ""
    primary_failure_type: str = ""
    secondary_failure_types: list[str] = Field(default_factory=list)
    failure_signature: str = ""
    owner_agent: str = ""
    missing_artifacts: list[str] = Field(default_factory=list)
    first_failure_at: str = ""
    first_failure_event_id: str = ""
    final_status_label: str = ""
    terminal_state: str = ""
    failure_events: list[dict] = Field(default_factory=list)
    event_log_file: str = ""
    trace_id: str = ""
    created_at: datetime = Field(default_factory=datetime.now)


class EvidenceStore:
    def __init__(self, base_dir: Path | None = None) -> None:
        self.base_dir = base_dir or (settings.runtime_dir / "evidence")

    def record(self, record: EvidenceRecord) -> Path:
        run_dir = self.base_dir / record.run_id / record.phase_id
        run_dir.mkdir(parents=True, exist_ok=True)
        path = run_dir / f"{record.record_id}.json"
        path.write_text(record.model_dump_json(indent=2), encoding="utf-8")
        return path

    def list_records(self, run_id: str, phase_id: str) -> list[Path]:
        run_dir = self.base_dir / run_id / phase_id
        if not run_dir.exists():
            return []
        return sorted(run_dir.glob("*.json"))

    def read(self, path: Path) -> EvidenceRecord:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return EvidenceRecord.model_validate(payload)

    def latest_record_path(self) -> Path | None:
        if not self.base_dir.exists():
            return None
        records = sorted(
            self.base_dir.rglob("*.json"),
            key=lambda candidate: candidate.stat().st_mtime,
            reverse=True,
        )
        return records[0] if records else None

    def latest_record(self) -> tuple[Path | None, EvidenceRecord | None]:
        path = self.latest_record_path()
        if path is None:
            return None, None
        try:
            return path, self.read(path)
        except Exception:
            return path, None

    def recent_records(self, limit: int = 3) -> list[tuple[Path, EvidenceRecord]]:
        if not self.base_dir.exists():
            return []
        paths = sorted(
            self.base_dir.rglob("*.json"),
            key=lambda candidate: candidate.stat().st_mtime,
            reverse=True,
        )[: max(0, limit)]
        records: list[tuple[Path, EvidenceRecord]] = []
        for path in paths:
            try:
                records.append((path, self.read(path)))
            except Exception:
                continue
        return records
