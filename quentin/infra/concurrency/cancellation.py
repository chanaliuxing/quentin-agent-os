from __future__ import annotations

from dataclasses import dataclass
from threading import Event
from typing import Dict, Optional
from threading import Lock


class CancelledError(RuntimeError):
    pass


@dataclass
class CancellationToken:
    _event: Event = Event()
    _reason: Optional[str] = None

    def cancel(self, reason: Optional[str] = None) -> None:
        self._reason = reason
        self._event.set()

    def is_cancelled(self) -> bool:
        return self._event.is_set()

    def reason(self) -> Optional[str]:
        return self._reason

    def raise_if_cancelled(self) -> None:
        if self._event.is_set():
            raise CancelledError(self._reason or "cancelled")

    def wait(self, timeout: Optional[float] = None) -> bool:
        return self._event.wait(timeout)


class CancellationRegistry:
    """
    Minimal global registry:
    - trace_id/run_id -> CancellationToken
    - used by runtime/executor/tools to propagate cancellations.
    """

    def __init__(self) -> None:
        self._tokens: Dict[str, CancellationToken] = {}
        self._guard = Lock()

    def get_or_create(self, key: str) -> CancellationToken:
        cleaned = (key or "").strip()
        if not cleaned:
            cleaned = "unknown"
        with self._guard:
            tok = self._tokens.get(cleaned)
            if tok is None:
                tok = CancellationToken()
                self._tokens[cleaned] = tok
            return tok

    def cancel(self, key: str, reason: Optional[str] = None) -> None:
        tok = self.get_or_create(key)
        tok.cancel(reason)

    def pop(self, key: str) -> Optional[CancellationToken]:
        cleaned = (key or "").strip()
        with self._guard:
            return self._tokens.pop(cleaned, None)


_REGISTRY: Optional[CancellationRegistry] = None


def default_cancellation_registry() -> CancellationRegistry:
    global _REGISTRY
    if _REGISTRY is None:
        _REGISTRY = CancellationRegistry()
    return _REGISTRY
