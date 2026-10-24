from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional
import asyncio
import json
import warnings

from quentin.sleep.loop import SleepLoop as QuentinSleepLoop
from quentin.sleep.loop import SleepLoopConfig as QuentinSleepLoopConfig
from quentin.utils.time import now_iso


@dataclass
class SleepLoopConfig:
    state_path: Path = Path("data/loops/sleep_loop_state.json")


class SleepLoop:
    """
    Compatibility shim for legacy `meta_agent.evolution.sleep_loop`.

    Canonical implementation lives in `quentin.sleep.loop.SleepLoop`.
    """

    def __init__(
        self,
        memory_fabric: Optional[Any] = None,
        skill_miner: Optional[Any] = None,
        skill_promotion: Optional[Any] = None,
        config: Optional[SleepLoopConfig] = None,
    ) -> None:
        _ = (skill_miner, skill_promotion)  # kept for backward-compatible constructor shape
        self.config = config or SleepLoopConfig()
        self.config.state_path.parent.mkdir(parents=True, exist_ok=True)
        self._impl = QuentinSleepLoop(
            memory_fabric=memory_fabric,
            config=QuentinSleepLoopConfig(),
            repo_root=".",
        )
        warnings.warn(
            "meta_agent.evolution.sleep_loop.SleepLoop is deprecated; "
            "use quentin.sleep.loop.SleepLoop instead.",
            DeprecationWarning,
            stacklevel=2,
        )

    def run_once(self) -> Dict[str, Any]:
        report = asyncio.run(self._impl.run_once())
        out = {
            "last_run_at": now_iso(),
            "sleep_report": report.to_dict() if hasattr(report, "to_dict") else {},
            "source": "meta_agent.evolution.sleep_loop",
        }
        with self.config.state_path.open("w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, indent=2)
        return out

