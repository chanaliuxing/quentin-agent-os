from __future__ import annotations

import os
from typing import Any, Dict, Optional
from quentin.models.router import ModelInfo
from quentin.models.routing_policies.base import RoutingPolicy

class DefaultRoutingPolicy(RoutingPolicy):
    """
    Default routing logic extracted from ModelRouter.
    """
    def __init__(self, router: Any, priority: int = 0):
        self.router = router
        self._priority = priority

    @property
    def id(self) -> str:
        return "default"

    @property
    def priority(self) -> int:
        return self._priority

    def route(self, mode: str, task_type: str, metadata: Dict[str, Any]) -> Optional[ModelInfo]:
        # Legacy-like routing
        model_name = self.router.choose_model(
            task_type=task_type,
            domain=(mode or None),
            preference=metadata.get("preference", "balanced")
        )
        if model_name and model_name in self.router.models:
            return self.router.models[model_name]
        return None
