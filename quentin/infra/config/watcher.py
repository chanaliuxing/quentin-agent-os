from __future__ import annotations

import os
import time
import logging
import threading
from pathlib import Path
from typing import Dict, Any, Optional, Callable, List

logger = logging.getLogger(__name__)

class ConfigWatcher:
    """
    Automated Hot-Reloading for Quentin configuration.
    Aligned with OpenClaw's config-reload mechanism.
    """
    def __init__(self, watch_files: List[str] = [".env", "config/model_router_rules.json"]):
        self.watch_files = [Path(f) for f in watch_files]
        self._last_mtimes: Dict[Path, float] = {}
        self._callbacks: List[Callable] = []
        self._running = False
        self._thread: Optional[threading.Thread] = None

    def register_callback(self, callback: Callable):
        self._callbacks.append(callback)

    def start(self, interval_sec: int = 2):
        self._running = True
        self._thread = threading.Thread(target=self._watch_loop, args=(interval_sec,), daemon=True)
        self._thread.start()
        logger.info(f"ConfigWatcher: Started monitoring {len(self.watch_files)} files.")

    def _watch_loop(self, interval: int):
        while self._running:
            changed = False
            for f in self.watch_files:
                if not f.exists(): continue
                
                mtime = f.stat().st_mtime
                if f not in self._last_mtimes:
                    self._last_mtimes[f] = mtime
                    continue
                
                if mtime > self._last_mtimes[f]:
                    logger.info(f"ConfigWatcher: Detected change in {f}")
                    self._last_mtimes[f] = mtime
                    changed = True
            
            if changed:
                for cb in self._callbacks:
                    try: cb()
                    except Exception as e: logger.error(f"Config reload callback failed: {e}")
            
            time.sleep(interval)

    def stop(self):
        self._running = False

# Global singleton
config_watcher = ConfigWatcher()
