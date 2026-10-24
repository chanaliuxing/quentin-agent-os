from __future__ import annotations

import json
import logging
import urllib.request
from typing import Any, Callable, Dict, Optional

from quentin.infra.channels.provider import ChannelProvider

logger = logging.getLogger(__name__)


class WebhookChannelAdapter(ChannelProvider):
    """
    Minimal webhook adapter that follows the unified ChannelProvider contract.
    """

    def __init__(self, endpoint_url: str, token: str = "", secret: str = "") -> None:
        self.endpoint_url = str(endpoint_url or "").strip()
        self.token = str(token or "").strip()
        self.secret = str(secret or "").strip()
        self._on_message: Optional[Callable[[Dict[str, Any]], Any]] = None
        self._running = False

    @property
    def provider_id(self) -> str:
        return "webhook"

    async def start(self) -> None:
        self._running = True

    async def stop(self) -> None:
        self._running = False

    async def send_text(self, target_id: str, text: str, **kwargs: Any) -> None:
        payload = {
            "target_id": str(target_id or ""),
            "text": str(text or ""),
            "metadata": kwargs.get("metadata") if isinstance(kwargs.get("metadata"), dict) else {},
        }
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        if self.secret:
            headers["X-Webhook-Secret"] = self.secret
        req = urllib.request.Request(
            url=self.endpoint_url,
            data=data,
            method="POST",
            headers=headers,
        )
        try:
            with urllib.request.urlopen(req, timeout=15):
                return None
        except Exception as exc:
            logger.error("Webhook adapter send failed: %s", exc)
            raise

    def set_on_message(self, callback: Callable[[Dict[str, Any]], Any]) -> None:
        self._on_message = callback

    def inject_inbound(self, payload: Dict[str, Any]) -> None:
        """
        Test/development helper to inject inbound webhook payloads.
        """
        if callable(self._on_message):
            self._on_message(dict(payload or {}))

    async def deliver_inbound(self, payload: Dict[str, Any]) -> None:
        if self._on_message is None:
            return
        try:
            result = self._on_message(dict(payload or {}))
            if hasattr(result, "__await__"):
                await result
        except Exception:
            logger.exception("Webhook adapter inbound callback failed")


# Backwards compatibility alias.
WebhookAdapter = WebhookChannelAdapter
