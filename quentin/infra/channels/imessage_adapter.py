from __future__ import annotations

import logging
import asyncio
import subprocess
from typing import Optional
from .base import ChannelAdapter, InboundMessage

from .imessage_monitor import IMessageMonitor

logger = logging.getLogger(__name__)

class IMessageAdapter(ChannelAdapter):
    """
    Adapter for iMessage (macOS).
    Sending: Uses `osascript`.
    Reading: Uses `IMessageMonitor` to poll chat.db.
    """
    def __init__(self):
        super().__init__("imessage")
        self._monitor = None

    async def _on_new_imessage(self, sender: str, text: str):
        if self._on_message_callback:
            inbound = InboundMessage(
                text=text,
                sender_id=sender,
                channel_id="imessage",
                metadata={"chat_id": sender}
            )
            await self._on_message_callback(inbound)

    async def start(self):
        if subprocess.run(["uname"], capture_output=True, text=True).stdout.strip() != "Darwin":
            logger.error("iMessage adapter only works on macOS.")
            return
        
        # Start the DB monitor
        self._monitor = IMessageMonitor(self._on_new_imessage)
        asyncio.create_task(self._monitor.start())
        logger.info("iMessage adapter ready (Send/Receive mode).")

    async def stop(self):
        if self._monitor:
            self._monitor.stop()

    async def send_text(self, target_id: str, text: str, **kwargs):
        """
        Send iMessage using AppleScript.
        target_id: Phone number or email address.
        """
        # Escape quotes for AppleScript
        safe_text = text.replace('"', '"').replace("'", "'")
        
        script = f'''
        tell application "Messages"
            set targetService to 1st service whose service type = iMessage
            set targetBuddy to buddy "{target_id}" of targetService
            send "{safe_text}" to targetBuddy
        end tell
        '''
        
        try:
            proc = await asyncio.create_subprocess_exec(
                "osascript", "-e", script,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            stdout, stderr = await proc.communicate()
            if proc.returncode != 0:
                logger.error(f"iMessage send failed: {stderr.decode()}")
        except Exception as e:
            logger.error(f"iMessage execution error: {e}")
