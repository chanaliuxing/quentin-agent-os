from __future__ import annotations

import json
from pathlib import Path

from app.config import settings
from app.models import ProjectSpec


class SorRepository:
    def __init__(self, base_dir: Path | None = None) -> None:
        self.base_dir = base_dir or (settings.runtime_dir / "sor")

    def project_spec_path(self, run_id: str) -> Path:
        return self.base_dir / run_id / "project_spec.json"

    def load_project_spec(self, run_id: str) -> ProjectSpec:
        spec_path = self.project_spec_path(run_id)
        payload = json.loads(spec_path.read_text(encoding="utf-8"))
        return ProjectSpec.model_validate(payload)

    def save_project_spec(self, run_id: str, spec: ProjectSpec) -> Path:
        spec_path = self.project_spec_path(run_id)
        spec_path.parent.mkdir(parents=True, exist_ok=True)
        spec_path.write_text(spec.model_dump_json(indent=2), encoding="utf-8")
        return spec_path
