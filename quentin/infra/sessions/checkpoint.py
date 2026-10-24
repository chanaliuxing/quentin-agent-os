from __future__ import annotations

import json
import logging
import os
import shutil
from pathlib import Path
from typing import Any, Dict, Optional
from quentin.infra.fs.atomic import fs_safe

logger = logging.getLogger(__name__)

class SessionCheckpoint:
    """
    Handles persistence of Cognitive Loop state.
    Aligned with OpenClaw's session snapshotting logic.
    """
    def __init__(self, storage_dir: str = "data/sessions"):
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)

    def save_checkpoint(self, task_id: str, state: Dict[str, Any], force: bool = False):
        """
        Saves the current execution state if dirty or forced.
        """
        from .dirty_sync import dirty_sync
        dirty_sync.track_change(task_id, state)
        if not force and not dirty_sync.should_sync(task_id):
            return

        file_path = self.storage_dir / f"{task_id}.checkpoint.json"
        
        # Enhanced Metadata for Full Recovery
        checkpoint_data = {
            "task_id": task_id,
            "timestamp": now_utc_iso() if 'now_utc_iso' in globals() else str(datetime.now()),
            "state": state,
            "executor_context": state.get("context", {}), # Capture local vars
            "active_skills": state.get("active_skills", []),
            "_version": 2
        }
        
        fs_safe.write_json(file_path, checkpoint_data)
        dirty_sync.mark_synced(task_id)
        logger.debug(f"Checkpoint saved for task {task_id}")

    def load_checkpoint(self, task_id: str) -> Optional[Dict[str, Any]]:
        """
        Loads a previous state if it exists.
        """
        file_path = self.storage_dir / f"{task_id}.checkpoint.json"
        data = fs_safe.read_json(file_path)
        if data:
            return data.get("state")
        return None

    def clear_checkpoint(self, task_id: str):
        """Removes the checkpoint after successful task completion."""
        file_path = self.storage_dir / f"{task_id}.checkpoint.json"
        if file_path.exists():
            file_path.unlink()
            logger.debug(f"Checkpoint cleared for task {task_id}")

# Helper for datetime
from datetime import datetime
def now_utc_iso():
    return datetime.utcnow().isoformat() + "Z"

# Global instance
checkpoint_manager = SessionCheckpoint()
