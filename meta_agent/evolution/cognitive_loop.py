from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional
import warnings

from quentin.cognitive.loop import CognitiveLoop as QuentinCognitiveLoop
from quentin.cognitive.loop import CognitiveTask


@dataclass
class CognitiveLoopConfig:
    domain: str = "maintenance"
    environment: str = "sandbox"
    fallback_input_text: str = "Run cognitive self-reflection cycle."


class CognitiveLoop:
    """
    Compatibility shim for legacy `meta_agent.evolution.cognitive_loop`.

    Canonical implementation lives in `quentin.cognitive.loop.CognitiveLoop`.
    """

    def __init__(self, memory_store: Any = None, config: Optional[CognitiveLoopConfig] = None):
        _ = memory_store  # Kept for backward-compatible constructor shape.
        self.config = config or CognitiveLoopConfig()
        self._impl = QuentinCognitiveLoop(repo_root=".")
        warnings.warn(
            "meta_agent.evolution.cognitive_loop.CognitiveLoop is deprecated; "
            "use quentin.cognitive.loop.CognitiveLoop instead.",
            DeprecationWarning,
            stacklevel=2,
        )

    def run(self, snapshot: Optional[Any] = None) -> Dict[str, Any]:
        meta: Dict[str, Any] = {"source": "meta_agent.evolution.cognitive_loop"}
        if snapshot is not None:
            meta["snapshot_type"] = snapshot.__class__.__name__

        task = CognitiveTask(
            input_text=self.config.fallback_input_text,
            domain=self.config.domain,
            environment=self.config.environment,
            metadata=meta,
        )
        result = self._impl.run_task(task)
        return {
            "task_id": result.task_id,
            "goal_id": result.goal_id,
            "done": bool(result.done),
            "done_confidence": float(result.done_confidence),
        }

