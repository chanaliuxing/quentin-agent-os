from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, Optional

from quentin.runtime.session_write_lock import acquire_session_write_lock
from quentin.tools.execution_parity import cron_tool
from quentin.tools.execution_parity import nodes_tool


@dataclass
class CronRunnerConfig:
    repo_root: str = "."
    tick_seconds: float = 10.0
    max_tasks_per_tick: int = 20
    lock_file: str = "data/runtime/cron_runner.state.json"
    reconcile_assignments: bool = True
    auto_assign_pending: bool = True


class CronRunner:
    """
    Thin runtime runner that executes cron due tasks via cron.tool(run_due).
    Uses a file lock to avoid multi-process duplicate triggering.
    """

    def __init__(self, config: Optional[CronRunnerConfig] = None) -> None:
        self.config = config or CronRunnerConfig()
        self.repo_root = Path(self.config.repo_root).resolve()
        self._running = False

    def _ctx(self) -> Any:
        return SimpleNamespace(metadata={"repo_root": str(self.repo_root)})

    def run_once(self) -> Dict[str, Any]:
        lock_path = (self.repo_root / self.config.lock_file).resolve()
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        hold = acquire_session_write_lock(session_file=lock_path, timeout_ms=1500, stale_ms=60_000)
        try:
            out = cron_tool(
                {
                    "action": "run_due",
                    "max_tasks": int(self.config.max_tasks_per_tick),
                },
                self._ctx(),
            )
            if not isinstance(out, dict):
                out = {"status": "error", "error": "invalid cron output"}
            out.setdefault("status", "ok")
            if bool(self.config.reconcile_assignments):
                try:
                    rec = nodes_tool(
                        {
                            "action": "reconcile_assignments",
                            "auto_assign_pending": bool(self.config.auto_assign_pending),
                        },
                        self._ctx(),
                    )
                except Exception as e:
                    rec = {"status": "error", "error": str(e)}
                out["assignment_reconcile"] = rec
            out["runner"] = "cron_runner"
            out["ts"] = time.time()
            lock_path.write_text(json.dumps({"last_run_ts": out["ts"], "last_result": out}, ensure_ascii=False, indent=2), encoding="utf-8")
            return out
        finally:
            hold["release"]()

    async def run_forever(self) -> None:
        self._running = True
        while self._running:
            _ = self.run_once()
            await asyncio.sleep(max(0.2, float(self.config.tick_seconds or 10.0)))

    def stop(self) -> None:
        self._running = False
