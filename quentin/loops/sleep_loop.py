from __future__ import annotations

"""
Legacy compatibility wrapper for SleepLoop.

This module previously contained an early, blueprint-oriented SleepLoop implementation.
The canonical implementation lives in `quentin.memory.sleep_loop`.
"""

from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, Optional
import asyncio
import logging

from quentin.memory.fabric import MemoryFabric
from quentin.memory.sleep_loop import SleepLoop as CanonicalSleepLoop, SleepLoopConfig as CanonicalSleepLoopConfig
from quentin.traces.core import JsonlTraceRecorder

logger = logging.getLogger(__name__)


@dataclass
class SleepConfig:
    trace_window_hours: int = 24
    max_traces_for_summary: int = 100
    max_traces_for_skills: int = 50
    enable_blueprint_scan: bool = False
    blueprint_min_score: float = 0.6
    blueprint_patch_limit: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class SleepLoop:
    """
    Compatibility API:
    - keeps a sync `run_once()` method returning a JSON-serializable dict
    - delegates real work to `quentin.memory.sleep_loop.SleepLoop` (async)
    """

    def __init__(
        self,
        *,
        repo_root: str | Path = ".",
        config: Optional[SleepConfig] = None,
        memory_fabric: Optional[MemoryFabric] = None,
        council: Any = None,
        trace_recorder: Any = None,
        skill_library: Any = None,
    ) -> None:
        root = Path(repo_root).resolve()
        self.repo_root = root
        self.config = config or SleepConfig()

        fabric = memory_fabric or MemoryFabric(db_path=root / "data" / "memory.db", use_postgres=False)
        recorder = trace_recorder or JsonlTraceRecorder(repo_root=root)

        canonical_cfg = CanonicalSleepLoopConfig(
            max_records_per_run=int(self.config.max_traces_for_summary or 100),
        )
        self._inner = CanonicalSleepLoop(
            memory_fabric=fabric,
            config=canonical_cfg,
            council=council,
            trace_recorder=recorder,
            skill_library=skill_library,
        )

    def run_once(self) -> Dict[str, Any]:
        try:
            report = asyncio.run(self._inner.run_once())
        except RuntimeError:
            # If already in an event loop, do a best-effort fallback.
            report = self._inner.run_once()  # type: ignore[misc]
        if hasattr(report, "to_dict"):
            return report.to_dict()
        if isinstance(report, dict):
            return report
        return {"status": "ok", "result": str(report)}

