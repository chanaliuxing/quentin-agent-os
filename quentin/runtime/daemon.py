from __future__ import annotations

import os
import time
import logging
from pathlib import Path
from typing import Optional, Any, Dict, List
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

from quentin.cognitive.loop import CognitiveLoop, CognitiveTask
from quentin.runtime.system_events import SystemEventQueue

logger = logging.getLogger(__name__)

class ContextualWakefulnessHandler(FileSystemEventHandler):
    """
    P5: Ported from OpenClaw's node-service.ts.
    Enhanced with Pattern-based Waker (Content Scanning).
    """
    def __init__(self, cognitive_loop: CognitiveLoop, repo_root: Path):
        self.cognitive_loop = cognitive_loop
        self.repo_root = repo_root
        self.last_event_ts = 0.0
        self.debounce_sec = 5.0
        # P5: OpenClaw Parity - High-value patterns
        self.wake_patterns = [
            re.compile(r"ERROR|FATAL|EXCEPTION", re.IGNORECASE),
            re.compile(r"TODO|FIXME|HACK", re.IGNORECASE),
            re.compile(r"FAILED|REJECTED", re.IGNORECASE),
        ]

    def on_modified(self, event):
        if event.is_directory:
            return
        
        rel_path = Path(event.src_path).relative_to(self.repo_root)
        
        # 1. Path Filtering
        if not (str(rel_path).startswith(("logs/", "mutable/", "generated/")) or rel_path.name in ("TODO.md", "governance.yaml")):
            return

        now = time.monotonic()
        if (now - self.last_event_ts) < self.debounce_sec:
            return
            
        # 2. Content Scanning (Pattern-based Waker)
        try:
            full_path = Path(event.src_path)
            # Read last 4KB to avoid massive file reads
            with open(full_path, "rb") as f:
                if full_path.stat().st_size > 4096:
                    f.seek(-4096, 2)
                content = f.read().decode("utf-8", errors="ignore")
                
            should_wake = any(p.search(content) for p in self.wake_patterns)
            if not should_wake and rel_path.name != "TODO.md":
                return
        except Exception:
            return # Silent fail for inaccessible files

        self.last_event_ts = now
        logger.info(f"Wakefulness: Pattern match detected in {rel_path}. Triggering silent perception.")
        
        # 3. Trigger Silent Perception Task (Shadow Execution)
        task = CognitiveTask(
            input_text=f"Environment change detected in {rel_path}. Content matches wake patterns. Update internal state.",
            domain="maintenance",
            metadata={
                "is_daemon_event": True, 
                "source_file": str(rel_path),
                "is_silent": True # Surgery Five: Shadow Execution
            }
        )
        
        # Execute in background (CRON lane)
        try:
            print(f"🔔 [Wakefulness] Pattern match: {rel_path}. Shadow task demanded.")
            # In a real daemon, we would use a non-blocking queue
            # asyncio.create_task(self.cognitive_loop.run_task_async(task))
        except Exception as e:
            logger.error(f"Wakefulness: Failed to trigger task: {e}")

class HeartbeatRunner:
    """
    P5: Ported from OpenClaw's heartbeat-runner.ts.
    Proactively checks system status with Adaptive Pacing.
    """
    def __init__(self, cognitive_loop: CognitiveLoop, repo_root: Path):
        self.loop = cognitive_loop
        self.repo_root = repo_root
        self._stop = False
        
        # P5: Surgery Seventy-one - Adaptive Pacing (OpenClaw Parity)
        from quentin.cognitive.perception.adaptive_engine import AdaptivePerceptionEngine
        self.pacing_engine = AdaptivePerceptionEngine()

    async def run(self):
        logger.info("Heartbeat: Adaptive proactive sensing active.")
        while not self._stop:
            try:
                # 1. Calculate next sleep interval based on current density
                interval = self.pacing_engine.get_current_interval()
                
                # 2. Standard Heartbeat Logic (OpenClaw style)
                # ... check HEARTBEAT.md, system health ...
                
                # If we detect a physical change event in the system, we'd record it:
                # self.pacing_engine.record_action()
                
            except Exception as e:
                logger.error(f"Heartbeat: Error during pulse: {e}")
            
            await asyncio.sleep(interval)

    def stop(self):
        self._stop = True

class TaylorDaemon:
    """
    Background daemon for Quentin Brain.
    """
    def __init__(self, repo_root: str, cognitive_loop: CognitiveLoop):
        self.repo_root = Path(repo_root).resolve()
        self.cognitive_loop = cognitive_loop
        self.observer = Observer()

    def start(self):
        handler = ContextualWakefulnessHandler(self.cognitive_loop, self.repo_root)
        self.observer.schedule(handler, str(self.repo_root), recursive=True)
        self.observer.start()
        logger.info(f"TaylorDaemon: Started monitoring {self.repo_root}")
        print(f"🚀 [Daemon] Taylor is now AWAKE and monitoring {self.repo_root}...")

    def stop(self):
        self.observer.stop()
        self.observer.join()
        logger.info("TaylorDaemon: Stopped.")

if __name__ == "__main__":
    # Test entry point
    logging.basicConfig(level=logging.INFO)
    loop = CognitiveLoop(repo_root=".")
    daemon = TaylorDaemon(repo_root=".", cognitive_loop=loop)
    try:
        daemon.start()
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        daemon.stop()
