from __future__ import annotations

from typing import Any, Dict, List, Protocol, runtime_checkable

@runtime_checkable
class EventStoreBackend(Protocol):
    """
    Backend interface for storing and retrieving system events (P2-C).
    """
    def enqueue_event(self, event: Dict[str, Any]) -> None:
        """Append a new event."""
        ...

    def drain_events(self, session_id: str, limit: int = 100) -> List[Dict[str, Any]]:
        """Retrieve and remove events for a session (queue behavior)."""
        ...

    def peek_events(self, session_id: str, limit: int = 100) -> List[Dict[str, Any]]:
        """Retrieve events without removing them."""
        ...

    def list_sessions(self) -> List[str]:
        """List active session IDs."""
        ...
