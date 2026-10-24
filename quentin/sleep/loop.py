from __future__ import annotations

"""
Sleep loop canonical entrypoint.

The canonical implementation lives in `quentin.sleep.loop_impl`.

`quentin.memory.sleep_loop` remains as a legacy import path and re-exports from the canonical
module for backward compatibility.
"""

from quentin.sleep.loop_impl import SleepLoop, SleepLoopConfig, SleepLoopReport  # noqa: F401

__all__ = [
    "SleepLoop",
    "SleepLoopConfig",
    "SleepLoopReport",
]
