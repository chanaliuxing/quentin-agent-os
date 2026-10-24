from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

@dataclass
class AdaptiveRouterPolicy:
    """
    P4-C: Adaptive Router Policy
    Dynamically adjustable routing parameters.
    """
    provider_priority: List[str] = field(default_factory=lambda: ["ollama", "openai", "anthropic"])
    compaction_strategy: str = "token_limit"
    compaction_threshold: int = 4000
    max_retries: int = 3
    failover_enabled: bool = True
    
    def update_from_metrics(self, metrics: Dict[str, Any]) -> None:
        """
        Dynamically tune parameters based on observed metrics.
        """
        error_rate = metrics.get("error_rate", 0.0)
        if error_rate > 0.1:
            self.max_retries = min(5, self.max_retries + 1)
        elif error_rate < 0.01:
            self.max_retries = max(1, self.max_retries - 1)
        
        latency = metrics.get("latency_p95", 0)
        if latency > 5000 and self.provider_priority[0] == "ollama":
             # If local Ollama is too slow, move it down in priority
             self.provider_priority = ["openai", "ollama", "anthropic"]
        elif latency < 1000 and "ollama" in self.provider_priority:
             # If latency is good, prefer local Ollama to save cost
             if "ollama" in self.provider_priority:
                 self.provider_priority.remove("ollama")
                 self.provider_priority.insert(0, "ollama")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "provider_priority": self.provider_priority,
            "compaction_strategy": self.compaction_strategy,
            "compaction_threshold": self.compaction_threshold,
            "max_retries": self.max_retries,
            "failover_enabled": self.failover_enabled
        }
