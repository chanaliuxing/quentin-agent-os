from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Callable
import uuid

@dataclass
class InboundMessage:
    text: str
    sender_id: str
    channel_id: str
    message_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    metadata: Dict[str, Any] = field(default_factory=dict)

class ChannelAdapter(ABC):
    """
    Base class for communication channels (Telegram, WhatsApp, etc.)
    Inspired by OpenClaw's ChannelMessagingAdapter.
    """
    def __init__(self, name: str):
        self.name = name
        self._on_message_callback: Optional[Callable[[InboundMessage], Any]] = None

    def set_on_message(self, callback: Callable[[InboundMessage], Any]):
        self._on_message_callback = callback

    @abstractmethod
    async def start(self):
        """Start the channel listener."""
        ...

    @abstractmethod
    async def stop(self):
        """Stop the channel listener."""
        ...

    @abstractmethod
    async def send_text(self, target_id: str, text: str, **kwargs):
        """Send a text message back to the phone."""
        ...
