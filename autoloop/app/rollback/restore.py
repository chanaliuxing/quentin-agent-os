from __future__ import annotations

import json
from pathlib import Path

from app.config import settings
from app.rollback.checkpoints import CheckpointRef


class RestoreManager:
    def __init__(self, base_dir: Path | None = None) -> None:
        self.base_dir = base_dir or (settings.runtime_dir / "checkpoints")

    def save_artifact_snapshot(self, *, checkpoint: CheckpointRef, artifacts: dict) -> Path:
        run_dir = self.base_dir / checkpoint.run_id / checkpoint.phase_id
        run_dir.mkdir(parents=True, exist_ok=True)
        path = run_dir / f"{checkpoint.checkpoint_id}_artifacts.json"
        path.write_text(json.dumps(artifacts, indent=2), encoding="utf-8")
        return path

    def restore_artifacts(self, *, checkpoint: CheckpointRef) -> dict:
        path = self.base_dir / checkpoint.run_id / checkpoint.phase_id / f"{checkpoint.checkpoint_id}_artifacts.json"
        if not path.exists():
            return dict(checkpoint.snapshot.get("artifacts", {}))
        return json.loads(path.read_text(encoding="utf-8"))
