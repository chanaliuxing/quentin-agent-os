from __future__ import annotations

import asyncio
import time
import logging
from typing import List, Optional, Callable, Any

logger = logging.getLogger(__name__)

class MessageCoalescer:
    """
    Atomic-Level Message Coalescing.
    Prevents notification spam by merging rapid-fire short messages.
    Matches OpenClaw's BlockReplyPipeline parameters.
    """
    def __init__(self, 
                 callback: Callable[[str], Any],
                 min_chars: int = 100, 
                 max_chars: int = 2000, 
                 wait_sec: float = 2.0):
        self.callback = callback
        self.min_chars = min_chars
        self.max_chars = max_chars
        self.wait_sec = wait_sec
        self._buffer: List[str] = []
        self._last_push_time = 0
        self._task: Optional[asyncio.Task] = None

    async def push(self, fragment: str):
        """Adds a message fragment to the buffer."""
        self._buffer.append(fragment)
        current_len = sum(len(f) for f in self._buffer)
        
        # If buffer is huge, flush immediately
        if current_len >= self.max_chars:
            await self.flush()
            return

        # Start a debounce timer
        if self._task:
            self._task.cancel()
        self._task = asyncio.create_task(self._wait_and_flush())

    async def _wait_and_flush(self):
        await asyncio.sleep(self.wait_sec)
        await self.flush()

    async def flush(self):
        if not self._buffer:
            return
        
        combined = "\n".join(self._buffer)
        self._buffer = []
        self._last_push_time = time.time()
        
        if asyncio.iscoroutinefunction(self.callback):
            await self.callback(combined)
        else:
            self.callback(combined)
