from __future__ import annotations

import logging
import asyncio
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional
from .base import ChannelAdapter, InboundMessage

logger = logging.getLogger(__name__)

class TelegramAdapter(ChannelAdapter):
    """
    Adapter for Telegram Bot API.
    """
    def __init__(self, token: str):
        super().__init__("telegram")
        self.token = token
        self._application = None
        self._is_running = False

    async def start(self):
        try:
            from telegram.ext import ApplicationBuilder, MessageHandler, filters, ContextTypes
            from telegram import Update
        except ImportError:
            logger.error("telegram-adapter: python-telegram-bot not installed.")
            return

        async def _msg_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
            if not update.message:
                return
            
            text = update.message.text or update.message.caption or ""
            sender_id = str(update.message.from_user.id)
            chat_id = update.message.chat_id
            
            attachments = []
            
            # Handle Photos
            if update.message.photo:
                # Get the largest version
                photo = update.message.photo[-1]
                file = await context.bot.get_file(photo.file_id)
                
                from .media import media_processor
                # Download to memory buffer
                buf = await file.download_as_bytearray()
                file_path = await media_processor.save_buffer(bytes(buf), "jpg")
                
                attachments.append({
                    "type": "image",
                    "path": file_path,
                    "b64": media_processor.to_base64(file_path)
                })

            inbound = InboundMessage(
                text=text,
                sender_id=sender_id,
                channel_id="telegram",
                metadata={
                    "chat_id": chat_id,
                    "username": update.message.from_user.username,
                    "attachments": attachments
                }
            )
            if self._on_message_callback:
                asyncio.create_task(self._on_message_callback(inbound))

        self._application = ApplicationBuilder().token(self.token).build()
        # Listen to both Text and Photos
        self._application.add_handler(MessageHandler(
            (filters.TEXT | filters.PHOTO) & (~filters.COMMAND), 
            _msg_handler
        ))
        
        await self._application.initialize()
        await self._application.start()
        await self._application.updater.start_polling()
        self._is_running = True
        logger.info("Telegram adapter started and polling.")

    async def stop(self):
        if self._application:
            await self._application.updater.stop()
            await self._application.stop()
            await self._application.shutdown()
        self._is_running = False

    async def send_text(self, target_id: str, text: str, **kwargs):
        try:
            if self._application:
                await self._application.bot.send_message(chat_id=target_id, text=text)
                return
            # One-shot fallback (without polling app)
            q = urllib.parse.urlencode({"chat_id": str(target_id), "text": str(text)})
            url = f"https://api.telegram.org/bot{self.token}/sendMessage?{q}"
            with urllib.request.urlopen(url, timeout=15):
                return
        except Exception as e:
            logger.error(f"Telegram send error: {e}")

    async def send_typing_action(self, target_id: str):
        """Sends the 'typing' status to the user."""
        if self._application:
            await self._application.bot.send_chat_action(chat_id=target_id, action="typing")
