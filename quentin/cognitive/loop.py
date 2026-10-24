from __future__ import annotations

"""
Cognitive loop canonical entrypoint.

This module re-exports the canonical implementation from `quentin.cognitive.loop_impl`.
It exists to provide a stable, discoverable import path for higher-level orchestration code.
"""

from quentin.cognitive.loop_impl import (  # noqa: F401
    CognitiveLoop,
    CognitiveTask,
    CognitiveResult,
    PlannerResult,
)

__all__ = [
    "CognitiveLoop",
    "CognitiveTask",
    "CognitiveResult",
    "PlannerResult",
]
