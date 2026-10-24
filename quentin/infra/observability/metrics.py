from __future__ import annotations
import json
import time
from pathlib import Path
from typing import Dict, Any

class MetricsCollector:
    """
    The Dashboard Backend.
    """
    def __init__(self, repo_root: str):
        self.repo_root = Path(repo_root)
        self.stats_path = self.repo_root / "data" / "metrics" / "daily_stats.json"
        self.stats_path.parent.mkdir(parents=True, exist_ok=True)
        self._load()

    def _load(self):
        if self.stats_path.exists():
            try:
                self.data = json.loads(self.stats_path.read_text())
            except:
                self.data = {"tokens": 0, "usd": 0.0, "calls": 0}
        else:
            self.data = {"tokens": 0, "usd": 0.0, "calls": 0}

    def record_usage(self, tokens: int, cost: float = 0.0):
        self.data["tokens"] += tokens
        self.data["usd"] += cost
        self.data["calls"] += 1
        self._save()

    def _save(self):
        try:
            self.stats_path.write_text(json.dumps(self.data, indent=2))
        except: pass
