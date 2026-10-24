from __future__ import annotations

import asyncio
import warnings
from typing import Any, Optional

from quentin.sleep.loop import SleepLoop as CanonicalSleepLoop
from quentin.sleep.loop import SleepLoopConfig, SleepLoopReport


class SleepLoop:
    """
    Legacy wrapper for the canonical SleepLoop at `quentin.sleep.loop`.
    Provides a sync `run_once()` for compatibility.
    """

    def __init__(
        self,
        *,
        config: Optional[SleepLoopConfig] = None,
        trace_recorder: Any = None,
        memory_fabric: Any = None,
        council: Any = None,
        repo_root: str | None = None,
    ) -> None:
        warnings.warn(
            "quentin.runtime.sleep_loop.SleepLoop is deprecated; use quentin.sleep.loop.SleepLoop",
            DeprecationWarning,
            stacklevel=2,
        )
        self._inner = CanonicalSleepLoop(
            memory_fabric=memory_fabric,
            config=config,
            council=council,
            trace_recorder=trace_recorder,
        )

    def run_once(self) -> SleepLoopReport:
        result = self._inner.run_once()
        if asyncio.iscoroutine(result):
            return asyncio.run(result)
        return result

__all__ = ["SleepLoop", "SleepLoopConfig", "SleepLoopReport"]
