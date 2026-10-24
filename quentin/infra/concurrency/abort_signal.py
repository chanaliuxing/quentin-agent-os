from __future__ import annotations

import asyncio
import logging
from typing import Dict, Optional, Set, Any
from threading import Lock

logger = logging.getLogger(__name__)

class AbortSignal:
    """
    P5: Ported from OpenClaw's AbortSignal.
    Allows for immediate cancellation of processes and model streaming.
    """
    def __init__(self, session_id: str):
        self.session_id = session_id
        self._aborted = False
        self._reason: Optional[str] = None
        self._on_abort_callbacks: Set[Any] = set()
        self._lock = Lock()
        self._async_event = asyncio.Event()

    def abort(self, reason: Optional[str] = None):
        with self._lock:
            if self._aborted:
                return
            self._aborted = True
            self._reason = reason
            self._async_event.set()
            
        logger.warning(f"AbortSignal: Session {self.session_id} ABORTED. Reason: {reason}")
        
        # Execute callbacks
        for cb in self._on_abort_callbacks:
            try:
                if asyncio.iscoroutinefunction(cb):
                    asyncio.create_task(cb(reason))
                else:
                    cb(reason)
            except Exception as e:
                logger.error(f"AbortSignal: Callback failed: {e}")

    @property
    def is_aborted(self) -> bool:
        return self._aborted

    @property
    def reason(self) -> Optional[str]:
        return self._reason

    def on_abort(self, callback: Any):
        with self._lock:
            self._on_abort_callbacks.add(callback)

    async def wait_for_abort(self):
        await self._async_event.wait()

class AbortRegistry:
    """
    Registry to manage AbortSignals across sessions.
    """
    def __init__(self):
        self._signals: Dict[str, AbortSignal] = {}
        self._lock = Lock()

    def get_signal(self, session_id: str) -> AbortSignal:
        with self._lock:
            if session_id not in self._signals:
                self._signals[session_id] = AbortSignal(session_id)
            return self._signals[session_id]

    def remove_signal(self, session_id: str):
        with self._lock:
            self._signals.pop(session_id, None)

# Global registry
abort_registry = AbortRegistry()
