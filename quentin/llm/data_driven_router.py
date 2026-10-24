from __future__ import annotations

"""
Legacy import path for the data-driven router.

Canonical location:
- `quentin.routing.data_driven_router`
"""

from quentin.routing.data_driven_router import (  # noqa: F401
    DataDrivenModelRouter,
    RoutingWeights,
)

__all__ = [
    "RoutingWeights",
    "DataDrivenModelRouter",
]

