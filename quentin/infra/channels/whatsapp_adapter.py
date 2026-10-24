from __future__ import annotations

import json
import logging
import urllib.request
from typing import Optional

from .base import ChannelAdapter

logger = logging.getLogger(__name__)


class WhatsAppAdapter(ChannelAdapter):
    """
    Minimal WhatsApp Cloud API sender adapter.
    - start/stop are no-op for now (send-only path).
    """

    def __init__(self, *, token: str, phone_number_id: str):
        super().__init__("whatsapp")
        self.token = str(token or "")
        self.phone_number_id = str(phone_number_id or "")
        self._running = False

    async def start(self):
        self._running = True

    async def stop(self):
        self._running = False

    async def send_text(self, target_id: str, text: str, **kwargs):
        if not (self.token and self.phone_number_id and target_id):
            raise RuntimeError("missing whatsapp token/phone_number_id/target_id")
        url = f"https://graph.facebook.com/v19.0/{self.phone_number_id}/messages"
        payload = {
            "messaging_product": "whatsapp",
            "to": str(target_id),
            "type": "text",
            "text": {"body": str(text)},
        }
        req = urllib.request.Request(
            url=url,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            method="POST",
            headers={
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=20):
                return
        except Exception as e:
            logger.error("WhatsApp send error: %s", e)
            raise

