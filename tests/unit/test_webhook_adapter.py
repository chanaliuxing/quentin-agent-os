from __future__ import annotations

from quentin.infra.channels.provider import ChannelProvider
from quentin.infra.channels.webhook_adapter import WebhookAdapter


def test_webhook_adapter_implements_channel_provider_contract() -> None:
    adapter: ChannelProvider = WebhookAdapter(endpoint_url="https://example.invalid/hook", token="t")
    assert adapter.provider_id == "webhook"
    assert callable(getattr(adapter, "set_on_message"))


def test_webhook_adapter_inbound_injection_calls_callback() -> None:
    adapter = WebhookAdapter(endpoint_url="https://example.invalid/hook")
    seen = []
    adapter.set_on_message(lambda payload: seen.append(payload))
    adapter.inject_inbound({"text": "hello"})
    assert seen and seen[0]["text"] == "hello"
