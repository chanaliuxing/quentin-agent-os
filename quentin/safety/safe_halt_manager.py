from __future__ import annotations
import logging
from typing import Dict, Any, List

logger = logging.getLogger(__name__)

class SafeHaltManager:
    """
    P8-D: Safe Halt Manager
    Autonomous shutdown trigger for catastrophic failures.
    """
    def __init__(self) -> None:
        self.halt_active: bool = False
        self.reasons: List[str] = []

    def check_and_trigger(self, telemetry: Dict[str, Any]) -> bool:
        if telemetry.get("safety_incident_count", 0) > 10:
            self.trigger_halt("high_safety_incident_spike")
            return True
        
        if telemetry.get("system_error_rate", 0.0) > 0.5:
            self.trigger_halt("catastrophic_error_rate")
            return True
            
        return False

    def trigger_halt(self, reason: str) -> None:
        self.halt_active = True
        self.reasons.append(reason)
        logger.critical("SYSTEM HALTED: %s", reason)

    def resume(self) -> None:
        self.halt_active = False
        self.reasons.clear()
        logger.info("System resumed from halt.")
