from __future__ import annotations
import json
import os
import time
from pathlib import Path
from typing import List, Dict, Any
from dataclasses import asdict
from quentin.ops.control_tower import TowerSnapshot

class ControlTowerStore:
    """
    P11-A: Control Tower Store
    Persists tower snapshots for trend analysis.
    """
    def __init__(self, repo_root: str = ".") -> None:
        self.log_path = Path(repo_root) / "data" / "ops" / "control_tower_snapshots.jsonl"
        self.log_path.parent.mkdir(parents=True, exist_ok=True)

    def save_snapshot(self, snapshot: TowerSnapshot) -> None:
        record = asdict(snapshot)
        with open(self.log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    def load_recent(self, limit: int = 10) -> List[Dict[str, Any]]:
        if not self.log_path.exists():
            return []
        
        with open(self.log_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
            return [json.loads(L) for L in lines[-limit:]]
