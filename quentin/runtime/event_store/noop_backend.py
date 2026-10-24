from __future__ import annotations

from typing import Any, Dict, List


class NoopEventStoreBackend:
    """
    No-op backend for system events (useful for tests / ultra-minimal runs).
    """

    @property
    def id(self) -> str:
        return "noop"

    def enqueue_event(self, event: Dict[str, Any]) -> None:  # noqa: ARG002
        return None

    def drain_events(self, session_id: str, limit: int = 100) -> List[Dict[str, Any]]:  # noqa: ARG002
        return []

    def peek_events(self, session_id: str, limit: int = 100) -> List[Dict[str, Any]]:  # noqa: ARG002
        return []

    def list_sessions(self) -> List[str]:
        return []

