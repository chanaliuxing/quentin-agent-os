from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional
import logging

logger = logging.getLogger(__name__)

@dataclass
class SystemEvent:
    type: str
    source: str
    payload: Dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=lambda: 0.0)

class SystemBus:
    """
    L0: Central communication bus for the AI OS (P5).
    Replaces direct imports with loosely coupled event signaling.
    """
    def __init__(self) -> None:
        self._handlers: Dict[str, List[Callable[[SystemEvent], None]]] = {}

    def subscribe(self, event_type: str, handler: Callable[[SystemEvent], None]) -> None:
        if event_type not in self._handlers:
            self._handlers[event_type] = []
        self._handlers[event_type].append(handler)

    def publish(self, event: SystemEvent) -> None:
        import time
        event.timestamp = time.time()
        
        logger.debug(f"Bus: Publishing {event.type} from {event.source}")
        
        # Exact match handlers
        for handler in self._handlers.get(event.type, []):
            try:
                handler(event)
            except Exception as e:
                logger.error(f"Bus: Handler for {event.type} failed: {e}")
        
        # Wildcard handlers
        for handler in self._handlers.get("*", []):
            try:
                handler(event)
            except Exception:
                pass

# Global kernel bus instance
_BUS = SystemBus()

def get_system_bus() -> SystemBus:
    return _BUS
