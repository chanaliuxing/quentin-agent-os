from __future__ import annotations

import asyncio
import logging
import threading
from typing import Any, Dict, Optional

from quentin.models.routing_policies.base import RoutingPolicy
from quentin.routing.model_router import ModelInfo

logger = logging.getLogger(__name__)


def _run_coro_blocking(coro: Any, *, timeout_sec: float = 30.0) -> Any:
    """
    Run a coroutine from sync code, even when called under an active event loop.

    Strategy:
    - no running loop: asyncio.run
    - running loop: execute coroutine in a new thread with its own event loop
    """
    try:
        asyncio.get_running_loop()
        has_loop = True
    except RuntimeError:
        has_loop = False

    if not has_loop:
        return asyncio.run(coro)

    out: Dict[str, Any] = {}

    def _runner() -> None:
        try:
            out["result"] = asyncio.run(coro)
        except Exception as e:  # noqa: BLE001
            out["error"] = e

    t = threading.Thread(target=_runner, daemon=True)
    t.start()
    t.join(timeout=float(timeout_sec))
    if t.is_alive():
        raise TimeoutError(f"routing policy coroutine timed out after {timeout_sec}s")
    if "error" in out:
        raise out["error"]
    return out.get("result")


class MultiAgentRoutingPolicy(RoutingPolicy):
    """
    Routing policy that delegates model choice to MultiAgentCoordinator (v2).

    Enabled via:
    - QUENTIN_ROUTING_POLICY=multi_agent
    """

    def __init__(self, router: Any, priority: int = 10) -> None:
        self.router = router
        self._priority = priority

    @property
    def id(self) -> str:
        return "multi_agent"

    @property
    def priority(self) -> int:
        return self._priority

    def route(self, mode: str, task_type: str, metadata: Dict[str, Any]) -> Optional[ModelInfo]:
        try:
            from quentin.infra.logging import Tracer
            from quentin.config.settings import Settings
            from quentin.multi_agent.coordinator import MultiAgentCoordinator
        except Exception:
            return None

        candidates = list(getattr(self.router, "models", {}).keys())
        if not candidates:
            return None

        coord = MultiAgentCoordinator(
            tracer=Tracer(),
            model_router=self.router,
            settings=Settings(),
        )

        try:
            decision = _run_coro_blocking(
                coord.choose_model(
                    candidates=candidates,
                    task_meta={"domain": mode, "task_type": task_type, **(metadata or {})},
                )
            )
        except Exception as e:
            logger.debug("MultiAgentRoutingPolicy: choose_model failed: %s", e)
            return None

        chosen = None
        try:
            chosen = str(getattr(decision, "chosen_model", "") or "")
        except Exception:
            chosen = ""
        if chosen and chosen in getattr(self.router, "models", {}):
            return self.router.models[chosen]
        return None


__all__ = ["MultiAgentRoutingPolicy"]

