from __future__ import annotations

import asyncio
import logging
from typing import Optional

logger = logging.getLogger(__name__)

class TypingController:
    """
    Manages the 'Typing...' status on various channels.
    Aligned with OpenClaw's src/channels/typing.
    """
    def __init__(self, adapter: Any, chat_id: str):
        self.adapter = adapter
        self.chat_id = chat_id
        self._typing_task: Optional[asyncio.Task] = None

    async def start_typing(self):
        """Starts a loop that keeps the 'Typing...' status active."""
        if self._typing_task:
            return
        
        async def _loop():
            try:
                while True:
                    # Specific to Telegram for now, but extensible
                    if hasattr(self.adapter, "send_typing_action"):
                        await self.adapter.send_typing_action(self.chat_id)
                    await asyncio.sleep(4) # Telegram typing status lasts ~5s
            except asyncio.CancelledError:
                pass

        self._typing_task = asyncio.create_task(_loop())

    async def stop_typing(self):
        if self._typing_task:
            self._typing_task.cancel()
            self._typing_task = None
