from __future__ import annotations
import logging
import yaml
from pathlib import Path
from typing import Dict, Any, List
from .release_snapshot import ReleaseSnapshotManager

logger = logging.getLogger(__name__)

class ReleaseOrchestrator:
    def __init__(self, repo_root: str):
        self.repo_root = Path(repo_root)
        self.snapshot_mgr = ReleaseSnapshotManager(repo_root)
        self.config_path = self.repo_root / "config" / "openclaw_parity.yaml"

    def _load_current_flags(self) -> Dict[str, Any]:
        if not self.config_path.exists():
            return {}
        with open(self.config_path) as f:
            data = yaml.safe_load(f) or {}
            return data.get("feature_flags", {})

    def _save_flags(self, flags: Dict[str, Any]):
        data = {"feature_flags": flags}
        with open(self.config_path, "w") as f:
            yaml.dump(data, f)

    def promote_to_staging(self, feature_set: Dict[str, bool]) -> str:
        current = self._load_current_flags()
        snap_id = self.snapshot_mgr.create_snapshot(current, metadata={"action": "promote_staging", "target": feature_set})
        
        # Merge updates
        current.update(feature_set)
        self._save_flags(current)
        logger.info(f"Promoted to staging. Snapshot: {snap_id}")
        return snap_id

    def promote_to_prod(self, feature_set: Dict[str, bool]) -> str:
        # Same logic for now, but in real world might have different config files
        current = self._load_current_flags()
        snap_id = self.snapshot_mgr.create_snapshot(current, metadata={"action": "promote_prod", "target": feature_set})
        
        current.update(feature_set)
        self._save_flags(current)
        logger.info(f"Promoted to PROD. Snapshot: {snap_id}")
        return snap_id

    def rollback(self, snap_id: str) -> bool:
        snapshot = self.snapshot_mgr.load_snapshot(snap_id)
        if not snapshot:
            logger.error(f"Snapshot {snap_id} not found.")
            return False
            
        self._save_flags(snapshot.flags)
        logger.warning(f"ROLLED BACK to {snap_id}")
        return True
