from __future__ import annotations

import asyncio
from typing import Any

from quentin.infra.channels.contracts import (
    GatewayContractVersion,
    GatewayInboundMessage,
    GatewayOutboundMessage,
)
from quentin.infra.channels.webhook_adapter import WebhookChannelAdapter


def test_gateway_contract_models_defaults() -> None:
    inbound = GatewayInboundMessage(channel="webhook", sender_id="u1", chat_id="c1", text="hi")
    outbound = GatewayOutboundMessage(channel="webhook", target_id="c1", text="ok")
    version = GatewayContractVersion()
    assert inbound.tenant_id == "default"
    assert outbound.tenant_id == "default"
    assert "webhook" in version.compatible_channels
    assert "sse" in version.transport_modes


def test_webhook_adapter_send_and_inbound(monkeypatch) -> None:
    adapter = WebhookChannelAdapter(endpoint_url="https://example.com/hook", secret="s1")
    sent: dict[str, Any] = {}

    class _Resp:
        def __enter__(self):  # type: ignore[no-untyped-def]
            return self

        def __exit__(self, *args):  # type: ignore[no-untyped-def]
            return False

    def _fake_urlopen(req, timeout=0):  # type: ignore[no-untyped-def]
        sent["url"] = req.full_url
        sent["headers"] = dict(req.headers)
        sent["body"] = req.data.decode("utf-8")
        sent["timeout"] = timeout
        return _Resp()

    monkeypatch.setattr("urllib.request.urlopen", _fake_urlopen)
    inbound_seen: list[dict[str, Any]] = []

    async def _cb(payload):  # type: ignore[no-untyped-def]
        inbound_seen.append(dict(payload or {}))

    async def _run() -> None:
        await adapter.start()
        adapter.set_on_message(_cb)
        await adapter.send_text("chat-1", "hello", tenant_id="t1")
        await adapter.deliver_inbound({"channel": "webhook", "text": "in"})
        await adapter.stop()

    asyncio.run(_run())
    assert adapter.provider_id == "webhook"
    assert sent["url"] == "https://example.com/hook"
    assert "X-webhook-secret" in {str(k): v for k, v in sent["headers"].items()} or "X-Webhook-Secret" in sent["headers"]
    assert '"target_id": "chat-1"' in sent["body"]
    assert inbound_seen and inbound_seen[0]["text"] == "in"
