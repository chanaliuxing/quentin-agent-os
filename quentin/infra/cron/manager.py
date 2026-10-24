from __future__ import annotations

import logging
import asyncio
import json
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Optional, Callable
from quentin.infra.fs.atomic import fs_safe

logger = logging.getLogger(__name__)

class CronManager:
    """
    Persistent Cron Engine for scheduled brain tasks.
    Aligned with OpenClaw's src/cron.
    """
    def __init__(self, db_path: str = "data/cron_tasks.json"):
        self.db_path = Path(db_path)
        self._tasks: Dict[str, Dict[str, Any]] = self._load()
        self._running = False

    def _load(self) -> Dict[str, Any]:
        data = fs_safe.read_json(self.db_path)
        return data or {}

    def _save(self):
        fs_safe.write_json(self.db_path, self._tasks)

    def schedule_task(self, name: str, interval_sec: int, task_input: str, metadata: Dict = None):
        """Register a new recurring task."""
        self._tasks[name] = {
            "interval": interval_sec,
            "input": task_input,
            "last_run": 0,
            "metadata": metadata or {}
        }
        self._save()
        logger.info(f"Cron: Scheduled task '{name}' every {interval_sec}s")

    async def run_loop(self, loop_executor_fn: Callable[[str], Any]):
        """The main ticker loop that checks for pending tasks."""
        self._running = True
        logger.info("Cron Engine started.")
        while self._running:
            now = datetime.now().timestamp()
            for name, task in self._tasks.items():
                if now - task["last_run"] >= task["interval"]:
                    logger.info(f"Cron: Triggering task '{name}'")
                    task["last_run"] = now
                    # Trigger the brain asynchronously
                    asyncio.create_task(loop_executor_fn(task["input"]))
            
            self._save()
            await asyncio.sleep(10) # Check every 10 seconds

    def stop(self):
        self._running = False

# Global instance
cron_engine = CronManager()
