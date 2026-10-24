from __future__ import annotations

import logging
import time
import json
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

class SessionDeltaTracker:
    """
    Tier 0 Session Sync Optimization.
    Tracks byte-level deltas to determine when memory indexing is required.
    QUENTIN_DIRTY_BYTE_THRESHOLD defaults to 512 bytes.
    """
    def __init__(self, debounce_ms: int = 5000, dirty_threshold_bytes: int = 512):
        self.debounce_sec = debounce_ms / 1000.0
        self.dirty_threshold = dirty_threshold_bytes
        self._last_save_time: float = 0
        self._last_byte_size: int = 0
        self._accumulated_dirty_bytes: int = 0

    def is_dirty(self, current_state: Dict[str, Any]) -> bool:
        # P5: Precise Byte-level Monitoring
        current_str = json.dumps(current_state, ensure_ascii=False)
        current_size = len(current_str.encode("utf-8"))
        
        # Calculate delta
        delta = abs(current_size - self._last_byte_size)
        self._accumulated_dirty_bytes += delta
        self._last_byte_size = current_size

        # Rule 1: Immediate sync if huge change
        if self._accumulated_dirty_bytes > self.dirty_threshold:
            return True
            
        # Rule 2: Debounced sync for small changes
        if (time.time() - self._last_save_time) >= self.debounce_sec:
            if self._accumulated_dirty_bytes > 0:
                return True
            
        return False

    def mark_clean(self, state: Dict[str, Any]):
        self._last_save_time = time.time()
        self._accumulated_dirty_bytes = 0
        current_str = json.dumps(state, ensure_ascii=False)
        self._last_byte_size = len(current_str.encode("utf-8"))

# Global instance
delta_tracker = SessionDeltaTracker()
