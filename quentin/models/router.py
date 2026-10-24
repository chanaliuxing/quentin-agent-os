from __future__ import annotations

"""
Legacy import path for the unified model router.

Canonical location:
- `quentin.routing.model_router`
"""

from quentin.routing.model_router import (  # noqa: F401
    ModelInfo,
    ModelUsageStats,
    ModelRouteRequest,
    ModelRouteDecision,
    ModelRouterConfig,
    ModelRouter,
)

__all__ = [
    "ModelInfo",
    "ModelUsageStats",
    "ModelRouteRequest",
    "ModelRouteDecision",
    "ModelRouterConfig",
    "ModelRouter",
]

