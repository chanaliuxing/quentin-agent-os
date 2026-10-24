from __future__ import annotations

import logging
import asyncio
from typing import Optional
from .base import ChannelAdapter, InboundMessage

logger = logging.getLogger(__name__)

class SlackAdapter(ChannelAdapter):
    """
    Adapter for Slack (Socket Mode via slack_sdk).
    Requires SLACK_APP_TOKEN (xapp-) and SLACK_BOT_TOKEN (xoxb-).
    """
    def __init__(self, app_token: str, bot_token: str):
        super().__init__("slack")
        self.app_token = app_token
        self.bot_token = bot_token
        self.handler = None
        self._is_running = False

    async def start(self):
        try:
            from slack_bolt.app.async_app import AsyncApp
            from slack_bolt.adapter.socket_mode.async_handler import AsyncSocketModeHandler
        except ImportError:
            logger.error("slack-adapter: slack_bolt not installed. Run 'pip install slack_bolt'")
            return

        app = AsyncApp(token=self.bot_token)

        @app.event("message")
        async def handle_message_events(message, say):
            if message.get("subtype") is None and "text" in message:
                inbound = InboundMessage(
                    text=message["text"],
                    sender_id=message["user"],
                    channel_id="slack",
                    metadata={
                        "channel_id": message["channel"],
                        "ts": message["ts"]
                    }
                )
                if self._on_message_callback:
                    asyncio.create_task(self._on_message_callback(inbound))

        self.handler = AsyncSocketModeHandler(app, self.app_token)
        self._is_running = True
        logger.info("Slack adapter starting (Socket Mode)...")
        asyncio.create_task(self.handler.start_async())

    async def stop(self):
        if self.handler:
            await self.handler.close_async()
        self._is_running = False

    async def send_text(self, target_id: str, text: str, **kwargs):
        try:
            if self.handler and self.handler.app:
                await self.handler.app.client.chat_postMessage(
                    channel=target_id,
                    text=text
                )
                return
            # One-shot fallback (no Socket Mode runtime required)
            from slack_sdk.web.async_client import AsyncWebClient

            client = AsyncWebClient(token=self.bot_token)
            await client.chat_postMessage(channel=target_id, text=text)
        except Exception as e:
            logger.error(f"Slack send error: {e}")
