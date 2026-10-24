from __future__ import annotations
import json
import time
import hashlib
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Dict, Any, Optional

@dataclass
class ReleaseSnapshot:
    id: str
    timestamp: float
    flags: Dict[str, Any]
    config_hash: str
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2)

    @classmethod
    def from_json(cls, data: str) -> ReleaseSnapshot:
        return cls(**json.loads(data))

class ReleaseSnapshotManager:
    def __init__(self, repo_root: str):
        self.repo_root = Path(repo_root)
        self.snapshots_dir = self.repo_root / "data" / "releases"
        self.snapshots_dir.mkdir(parents=True, exist_ok=True)

    def create_snapshot(self, flags: Dict[str, Any], metadata: Optional[Dict[str, Any]] = None) -> str:
        ts = time.time()
        # Compute config hash (e.g. from openclaw_parity.yaml)
        config_path = self.repo_root / "config" / "openclaw_parity.yaml"
        config_hash = "unknown"
        if config_path.exists():
            config_hash = hashlib.sha256(config_path.read_bytes()).hexdigest()

        snap_id = f"rel_{int(ts)}"
        snapshot = ReleaseSnapshot(
            id=snap_id,
            timestamp=ts,
            flags=flags,
            config_hash=config_hash,
            metadata=metadata or {}
        )
        
        path = self.snapshots_dir / f"{snap_id}.json"
        path.write_text(snapshot.to_json())
        return snap_id

    def load_snapshot(self, snap_id: str) -> Optional[ReleaseSnapshot]:
        path = self.snapshots_dir / f"{snap_id}.json"
        if not path.exists(): return None
        return ReleaseSnapshot.from_json(path.read_text())

    def list_snapshots(self) -> list[str]:
        return sorted([p.stem for p in self.snapshots_dir.glob("rel_*.json")], reverse=True)
