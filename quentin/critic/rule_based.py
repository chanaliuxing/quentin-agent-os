from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict


@dataclass
class RuleBasedCritic:
    """
    Minimal rule-based critic placeholder.

    New code should prefer:
    - `quentin.critic.core.SimpleCritic` (LLM-based)
    - `quentin.critic.task_council.TaskCritic` (council-based)
    """

    def review(self, execution_summary: Dict[str, Any]) -> Dict[str, Any]:
        _ = execution_summary
        return {"feedback": "Good job (default)"}

