from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Any, Callable, Dict, Optional

class ChannelProvider(ABC):
    """
    Unified Channel Provider Protocol.
    Allows pluggable messaging adapters (Telegram, Slack, Discord, Gateway).
    """
    @property
    @abstractmethod
    def provider_id(self) -> str:
        """Unique identifier for this provider (e.g. 'telegram', 'slack')."""
        pass

    @abstractmethod
    async def start(self) -> None:
        """Initialize connection/polling."""
        pass

    @abstractmethod
    async def stop(self) -> None:
        """Cleanup resources."""
        pass

    @abstractmethod
    async def send_text(self, target_id: str, text: str, **kwargs: Any) -> None:
        """Send a text message to a specific target (chat_id, channel_id)."""
        pass

    @abstractmethod
    def set_on_message(self, callback: Callable[[Dict[str, Any]], Any]) -> None:
        """
        Register a callback for inbound messages.
        Callback payload should include:
        - channel: str
        - sender_id: str
        - chat_id: str
        - text: str
        - session_id: str (optional, derived if missing)
        """
        pass
