# meta_agent/blueprint/blueprint_loop.py
from __future__ import annotations

from meta_agent.evolution.blueprint_loop import BlueprintImprovementLoop


def run_blueprint_self_update_cycle(*, max_sections: int = 3) -> dict:
    """
    Backwards-compatible entrypoint.

    Canonical implementation lives in `meta_agent.evolution.blueprint_loop.BlueprintImprovementLoop`.
    """
    loop = BlueprintImprovementLoop()
    return loop.run(max_sections=max_sections)


__all__ = ["run_blueprint_self_update_cycle", "BlueprintImprovementLoop"]
