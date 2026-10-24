from __future__ import annotations

import asyncio
import time

from quentin.infra.channels.base import ChannelAdapter, InboundMessage
from quentin.infra.channels.listener_manager import ChannelListenerManager


class _FakeAdapter(ChannelAdapter):
    def __init__(self, fail_first: bool = False):
        super().__init__("fake")
        self.fail_first = fail_first
        self.started = 0

    async def start(self):
        self.started += 1
        if self.fail_first and self.started == 1:
            raise RuntimeError("boom")
        if self._on_message_callback:
            await self._on_message_callback(InboundMessage(text="a", sender_id="u", channel_id="fake", message_id="m1"))
            await self._on_message_callback(InboundMessage(text="b", sender_id="u", channel_id="fake", message_id="m2"))

    async def stop(self):
        return None

    async def send_text(self, target_id: str, text: str, **kwargs):
        _ = (target_id, text, kwargs)
        return None


def test_listener_manager_restarts_on_start_failure(monkeypatch):
    mgr = ChannelListenerManager()
    monkeypatch.setattr(mgr, "_build_adapter", lambda p, c: _FakeAdapter(fail_first=True))
    res = mgr.start("discord", config={})
    assert res["status"] == "ok"
    time.sleep(0.25)
    st = mgr.status("discord")
    assert st["status"] == "ok"
    assert st["count"] == 1
    assert int(st["listeners"][0].get("restart_count") or 0) >= 1
    assert str(st["listeners"][0].get("last_restart_reason") or "") in {"adapter_error", "network_error", "timeout", "rate_limit", "auth_error", "dns_error", "config_error", "unknown"}
    assert isinstance(st["listeners"][0].get("restart_reasons"), dict)
    mgr.stop("discord")


def test_listener_manager_restart_reason_taxonomy(monkeypatch):
    class _RateLimitAdapter(_FakeAdapter):
        async def start(self):
            self.started += 1
            raise RuntimeError("429 too many requests")

    mgr = ChannelListenerManager()
    monkeypatch.setattr(mgr, "_build_adapter", lambda p, c: _RateLimitAdapter(fail_first=False))
    res = mgr.start("discord", config={})
    assert res["status"] == "ok"
    time.sleep(0.2)
    st = mgr.status("discord")
    assert st["status"] == "ok"
    assert st["count"] == 1
    li = st["listeners"][0]
    assert li["last_restart_reason"] == "rate_limit"
    assert int((li.get("restart_reasons") or {}).get("rate_limit") or 0) >= 1
    mgr.stop("discord")


def test_listener_manager_rate_limit_drops(monkeypatch):
    class _BurstAdapter(_FakeAdapter):
        async def start(self):
            self.started += 1
            if self._on_message_callback:
                for i in range(20):
                    await self._on_message_callback(
                        InboundMessage(text=f"m{i}", sender_id="u", channel_id="fake", message_id=f"m{i}")
                    )

    mgr = ChannelListenerManager()
    monkeypatch.setenv("QUENTIN_LISTENER_RATE_LIMIT_PER_MIN", "10")
    monkeypatch.setattr(mgr, "_build_adapter", lambda p, c: _BurstAdapter(fail_first=False))
    res = mgr.start("telegram", config={})
    assert res["status"] == "ok"
    time.sleep(0.2)
    st = mgr.status("telegram")
    assert st["status"] == "ok"
    assert st["count"] == 1
    assert int(st["listeners"][0].get("dropped_count") or 0) >= 1
    mgr.stop("telegram")


def test_listener_manager_platform_backoff_policy_exposed(monkeypatch):
    class _FailAdapter(_FakeAdapter):
        async def start(self):
            self.started += 1
            raise RuntimeError("429 rate limit")

    mgr = ChannelListenerManager()
    monkeypatch.setenv("QUENTIN_LISTENER_BACKOFF_TELEGRAM_MAX_SEC", "12")
    monkeypatch.setattr(mgr, "_build_adapter", lambda p, c: _FailAdapter(fail_first=False))
    res = mgr.start("telegram", config={})
    assert res["status"] == "ok"
    time.sleep(0.2)
    st = mgr.status("telegram")
    assert st["status"] == "ok"
    assert st["count"] == 1
    li = st["listeners"][0]
    pol = dict(li.get("backoff_policy") or {})
    assert float(pol.get("max_sec") or 0.0) == 12.0
    assert float(pol.get("rate_limit_floor_sec") or 0.0) >= 1.0
    mgr.stop("telegram")
