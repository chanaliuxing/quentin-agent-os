from __future__ import annotations

import logging
import asyncio
import json
import urllib.request
from typing import Optional
from .base import ChannelAdapter, InboundMessage

logger = logging.getLogger(__name__)

class DiscordAdapter(ChannelAdapter):
    """
    Adapter for Discord Bot API (via discord.py).
    """
    def __init__(self, token: str):
        super().__init__("discord")
        self.token = token
        self.client = None
        self._is_running = False

    async def start(self):
        try:
            import discord
        except ImportError:
            logger.error("discord-adapter: discord.py not installed. Run 'pip install discord.py'")
            return

        intents = discord.Intents.default()
        intents.messages = True
        intents.message_content = True  # Required for reading content

        class MyClient(discord.Client):
            def __init__(self, adapter, *args, **kwargs):
                super().__init__(*args, **kwargs)
                self.adapter = adapter

            async def on_ready(self):
                logger.info(f'Discord adapter logged in as {self.user} (ID: {self.user.id})')

            async def on_message(self, message):
                # Ignore own messages
                if message.author.id == self.user.id:
                    return

                text = message.content or ""
                attachments = []

                # Handle Discord Attachments
                if message.attachments:
                    for attachment in message.attachments:
                        if any(attachment.filename.lower().endswith(ext) for x in ['jpg', 'jpeg', 'png']):
                            from .media import media_processor
                            content = await attachment.read()
                            file_path = await media_processor.save_buffer(content, attachment.filename.split('.')[-1])
                            
                            attachments.append({
                                "type": "image",
                                "path": file_path,
                                "b64": media_processor.to_base64(file_path)
                            })

                inbound = InboundMessage(
                    text=text,
                    sender_id=str(message.author.id),
                    channel_id="discord",
                    metadata={
                        "channel_id": message.channel.id,
                        "author_name": message.author.name,
                        "guild_id": message.guild.id if message.guild else None,
                        "attachments": attachments
                    }
                )
                
                if self.adapter._on_message_callback:
                    asyncio.create_task(self.adapter._on_message_callback(inbound))

        self.client = MyClient(self, intents=intents)
        
        # discord.py client.start() is blocking, so we wrap it
        self._is_running = True
        asyncio.create_task(self.client.start(self.token))

    async def stop(self):
        if self.client:
            await self.client.close()
        self._is_running = False

    async def send_text(self, target_id: str, text: str, **kwargs):
        try:
            if self.client:
                # target_id in Discord is channel_id
                channel = self.client.get_channel(int(target_id))
                if not channel:
                    # Try fetching if not in cache
                    try:
                        channel = await self.client.fetch_channel(int(target_id))
                    except Exception:
                        logger.error(f"Discord: Channel {target_id} not found.")
                        return
                await channel.send(text)
                return

            # One-shot REST fallback
            url = f"https://discord.com/api/v10/channels/{int(target_id)}/messages"
            data = json.dumps({"content": str(text)}).encode("utf-8")
            req = urllib.request.Request(
                url=url,
                data=data,
                method="POST",
                headers={
                    "Authorization": f"Bot {self.token}",
                    "Content-Type": "application/json",
                },
            )
            with urllib.request.urlopen(req, timeout=15):
                return
        except Exception as e:
            logger.error(f"Discord send error: {e}")
