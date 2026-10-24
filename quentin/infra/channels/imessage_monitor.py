from __future__ import annotations

import sqlite3
import os
import time
import logging
import asyncio
from pathlib import Path
from typing import List, Dict, Optional, Callable

logger = logging.getLogger(__name__)

class IMessageMonitor:
    """
    Monitors macOS iMessage database (chat.db) for new messages.
    Aligned with OpenClaw's imessage/monitor logic.
    """
    DB_PATH = Path("~/Library/Messages/chat.db").expanduser()

    def __init__(self, callback: Callable[[str, str], Any]):
        self.callback = callback
        self._last_id = 0
        self._running = False

    async def start(self):
        if not self.DB_PATH.exists():
            logger.error(f"iMessage DB not found at {self.DB_PATH}")
            return

        # Initialize last_id to current max to avoid processing old messages
        self._last_id = self._get_max_id()
        self._running = True
        logger.info(f"iMessage monitor started (Last ID: {self._last_id})")
        
        while self._running:
            try:
                new_messages = self._fetch_new_messages()
                for msg_id, sender, text in new_messages:
                    if text:
                        await self.callback(sender, text)
                    self._last_id = msg_id
            except Exception as e:
                logger.debug(f"iMessage poll error (likely permission): {e}")
            
            await asyncio.sleep(2) # Poll every 2 seconds

    def stop(self):
        self._running = False

    def _get_max_id(self) -> int:
        try:
            conn = sqlite3.connect(f"file:{self.DB_PATH}?mode=ro", uri=True)
            cursor = conn.cursor()
            cursor.execute("SELECT MAX(ROWID) FROM message")
            res = cursor.fetchone()[0]
            conn.close()
            return res or 0
        except:
            return 0

    def _fetch_new_messages(self) -> List[tuple]:
        messages = []
        try:
            # Connect in read-only mode to avoid locking
            conn = sqlite3.connect(f"file:{self.DB_PATH}?mode=ro", uri=True)
            cursor = conn.cursor()
            query = """
            SELECT 
                m.ROWID, 
                h.id as sender, 
                m.text 
            FROM message m
            JOIN handle h ON m.handle_id = h.ROWID
            WHERE m.ROWID > ? AND m.is_from_me = 0
            ORDER BY m.ROWID ASC
            """
            cursor.execute(query, (self._last_id,))
            messages = cursor.fetchall()
            conn.close()
        except Exception:
            pass
        return messages
