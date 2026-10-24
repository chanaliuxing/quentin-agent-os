from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from pathlib import Path

from app.config import settings


@dataclass
class ExecutionSummary:
    workflow_id: str
    phase_id: str
    primary_failure_type: str
    secondary_failure_types: list[str]
    first_failure_at: str
    first_failure_event_id: str
    final_status_label: str
    terminal_state: str
    finalized_at: str
    terminal_event_id: str
    recovery_action: str
    acceptance_status: str


class ExecutionSummaryStore:
    def __init__(self, base_dir: Path | None = None) -> None:
        self.base_dir = base_dir or (settings.runtime_dir / "evidence")

    def write(self, summary: ExecutionSummary) -> Path:
        run_dir = self.base_dir / summary.workflow_id / summary.phase_id
        run_dir.mkdir(parents=True, exist_ok=True)
        path = run_dir / "execution_summary.json"
        path.write_text(json.dumps(asdict(summary), ensure_ascii=False, indent=2), encoding="utf-8")
        return path
