from __future__ import annotations
import time
from typing import Dict, Any, List

class BlueTeamResponseOrchestrator:
    """
    P9-B: Blue Team Response Orchestrator
    Monitors and captures system responses during Red Team exercises.
    """
    def __init__(self) -> None:
        self.results: List[Dict[str, Any]] = []

    def capture_outcome(self, scenario_id: str, suppressed: bool, latency_ms: float) -> None:
        self.results.append({
            "scenario_id": scenario_id,
            "suppressed": suppressed,
            "latency_ms": latency_ms,
            "timestamp": time.time()
        })

    def get_summary(self) -> Dict[str, Any]:
        if not self.results: return {}
        success_count = sum(1 for r in self.results if r["suppressed"])
        return {
            "total_exercises": len(self.results),
            "suppression_rate": success_count / len(self.results),
            "avg_latency_ms": sum(r["latency_ms"] for r in self.results) / len(self.results)
        }
