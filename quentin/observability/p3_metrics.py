from __future__ import annotations
import time
import json
from pathlib import Path
from typing import Dict, Any, Optional

class P3MetricsAggregator:
    def __init__(self, repo_root: str):
        self.repo_root = Path(repo_root)
        self.metrics_path = self.repo_root / "data" / "metrics" / "p3_dashboard.json"
        self.metrics_path.parent.mkdir(parents=True, exist_ok=True)
        self._cache: Dict[str, Any] = {}

    def record(self, key: str, value: float):
        if key not in self._cache:
            self._cache[key] = []
        self._cache[key].append(value)
        # Simple rolling window
        if len(self._cache[key]) > 100:
            self._cache[key].pop(0)
    
    def snapshot(self) -> Dict[str, Any]:
        stats = {}
        for k, vals in self._cache.items():
            if not vals: continue
            stats[f"{k}_p95"] = sorted(vals)[int(len(vals) * 0.95)]
            stats[f"{k}_avg"] = sum(vals) / len(vals)
            stats[f"{k}_count"] = len(vals)
        
        self.metrics_path.write_text(json.dumps(stats, indent=2))
        return stats

p3_metrics = P3MetricsAggregator(".")
