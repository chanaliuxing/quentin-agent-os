from __future__ import annotations
import time
import math
import logging
from typing import List, Dict, Any
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

class MemoryDecayEngine:
    """
    P5: Ported from OpenClaw's memory management.
    Handles semantic importance decay and physical record expiration.
    """
    def __init__(self, decay_factor: float = 0.95, halflife_hours: int = 24):
        self.decay_factor = decay_factor
        self.halflife_hours = halflife_hours

    def calculate_decay(self, current_importance: float, last_updated: datetime) -> float:
        """
        Exponential time-based decay.
        """
        hours_passed = (datetime.now() - last_updated).total_seconds() / 3600.0
        # Formula: I = I0 * (0.5 ^ (t / halflife))
        decayed_importance = current_importance * (0.5 ** (hours_passed / self.halflife_hours))
        return max(0.0, min(1.0, decayed_importance))

    def apply_task_penalty(self, current_importance: float) -> float:
        """
        Slars importance when a task is finished to reduce noise.
        """
        return current_importance * 0.5

    def should_expire(self, importance: float, last_accessed: Optional[datetime]) -> bool:
        """
        Determines if a record should be physically culled.
        """
        if importance < 0.1:
            return True
        if last_accessed:
            days_inactive = (datetime.now() - last_accessed).days
            if days_inactive > 7 and importance < 0.3:
                return True
        return False
