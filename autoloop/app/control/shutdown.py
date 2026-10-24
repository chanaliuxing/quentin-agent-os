from __future__ import annotations

import signal
from dataclasses import dataclass
from datetime import datetime
from types import FrameType
from typing import Callable


@dataclass
class ShutdownState:
    shutdown_requested: bool = False
    signal_name: str = ""
    requested_at: str = ""
    termination_reason: str = ""


class ShutdownManager:
    def __init__(self) -> None:
        self.state = ShutdownState()
        self._previous: dict[int, Callable | int | None] = {}

    def install(self) -> None:
        for sig in (signal.SIGINT, signal.SIGTERM):
            self._previous[sig] = signal.getsignal(sig)
            signal.signal(sig, self._handle_signal)

    def restore(self) -> None:
        for sig, handler in self._previous.items():
            if handler is None:
                continue
            signal.signal(sig, handler)
        self._previous.clear()

    def _handle_signal(self, signum: int, _: FrameType | None) -> None:
        if not self.state.shutdown_requested:
            name = signal.Signals(signum).name
            self.state.shutdown_requested = True
            self.state.signal_name = name
            self.state.requested_at = datetime.now().isoformat()
            self.state.termination_reason = f"signal_{name.lower()}"
        raise KeyboardInterrupt

