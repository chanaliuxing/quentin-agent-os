# quentin/memory/sleep_loop.py
from __future__ import annotations

"""
Legacy import path for the SleepLoop.

The canonical implementation lives in `quentin.sleep.loop_impl` and is re-exported here to keep
backward compatibility for older imports.
"""

from quentin.sleep.loop_impl import SleepLoop, SleepLoopConfig, SleepLoopReport  # noqa: F401

__all__ = [
    "SleepLoop",
    "SleepLoopConfig",
    "SleepLoopReport",
]

