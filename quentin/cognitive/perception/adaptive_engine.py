from __future__ import annotations
import time
import logging
from typing import List

logger = logging.getLogger(__name__)

class AdaptivePerceptionEngine:
    """
    P5: Ported from OpenClaw's 'Adaptive Pacing'.
    Calculates the optimal perception frequency based on action density.
    """
    def __init__(self):
        self.action_timestamps: List[float] = []
        self.max_history = 5
        
        # Interval ranges in seconds
        self.MIN_INTERVAL = 0.5
        self.DEFAULT_INTERVAL = 2.0
        self.MAX_INTERVAL = 15.0

    def record_action(self):
        """Called whenever the agent performs a physical tool action."""
        self.action_timestamps.append(time.time())
        if len(self.action_timestamps) > self.max_history:
            self.action_timestamps.pop(0)

    def get_current_interval(self) -> float:
        """
        Computes the target sleep interval between perception turns.
        """
        if len(self.action_timestamps) < 2:
            return self.DEFAULT_INTERVAL
            
        # Calculate average gap between recent actions
        gaps = [
            self.action_timestamps[i] - self.action_timestamps[i-1]
            for i in range(1, len(self.action_timestamps))
        ]
        avg_gap = sum(gaps) / len(gaps)
        
        # P5: OpenClaw Parity Mapping
        if avg_gap < 3.0:
            interval = self.MIN_INTERVAL # Burst mode
        elif avg_gap < 10.0:
            interval = self.DEFAULT_INTERVAL # Standard mode
        else:
            interval = min(self.MAX_INTERVAL, avg_gap * 0.5) # Lurk mode
            
        logger.debug(f"AdaptiveEngine: Avg action gap {avg_gap:.1f}s -> Interval {interval:.1f}s")
        return interval

    def force_wake(self):
        """Immediately resets to high frequency."""
        self.action_timestamps = [time.time()] * self.max_history
