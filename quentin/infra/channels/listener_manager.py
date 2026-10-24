from __future__ import annotations

import asyncio
import logging
import threading
import time
from dataclasses import dataclass, field
from collections import deque
from typing import Any, Callable, Deque, Dict, List, Optional
import os

from quentin.infra.channels.base import ChannelAdapter, InboundMessage

logger = logging.getLogger(__name__)


@dataclass
class ListenerRuntime:
    platform: str
    adapter: ChannelAdapter
    loop: asyncio.AbstractEventLoop
    thread: threading.Thread
    started_at: float = field(default_factory=time.time)
    status: str = "starting"
    last_error: str = ""
    msg_seq: int = 0
    messages: List[Dict[str, Any]] = field(default_factory=list)
    restart_count: int = 0
    dropped_count: int = 0
    rate_limit_per_min: int = 120
    stop_flag: bool = False
    recent_arrivals: Deque[float] = field(default_factory=deque)
    last_restart_reason: str = ""
    restart_reasons: Dict[str, int] = field(default_factory=dict)
    backoff_profile: str = "exponential"
    backoff_policy: Dict[str, float] = field(default_factory=dict)


def _classify_restart_reason(err: Exception) -> str:
    txt = str(err or "").strip().lower()
    if not txt:
        return "unknown"
    if "rate limit" in txt or "429" in txt or "too many requests" in txt:
        return "rate_limit"
    if "timeout" in txt or "timed out" in txt:
        return "timeout"
    if "dns" in txt or "name or service not known" in txt:
        return "dns_error"
    if "401" in txt or "403" in txt or "unauthorized" in txt or "forbidden" in txt or "token" in txt:
        return "auth_error"
    if "connection" in txt or "network" in txt or "socket" in txt or "broken pipe" in txt or "reset by peer" in txt:
        return "network_error"
    if "unsupported platform" in txt:
        return "config_error"
    return "adapter_error"


def _resolve_backoff_policy(platform: str, profile: str) -> Dict[str, float]:
    p = str(platform or "").strip().lower()
    pf = str(profile or "exponential").strip().lower()
    # Platform presets: tune reconnect pressure for adapter/API behavior.
    presets: Dict[str, Dict[str, float]] = {
        "discord": {"initial_sec": 1.0, "max_sec": 30.0, "multiplier": 2.2, "rate_limit_floor_sec": 5.0},
        "slack": {"initial_sec": 1.5, "max_sec": 45.0, "multiplier": 2.0, "rate_limit_floor_sec": 8.0},
        "telegram": {"initial_sec": 0.75, "max_sec": 20.0, "multiplier": 1.8, "rate_limit_floor_sec": 3.0},
        "default": {"initial_sec": 0.5, "max_sec": 15.0, "multiplier": 2.0, "rate_limit_floor_sec": 4.0},
    }
    base = dict(presets.get(p) or presets["default"])
    if pf == "linear":
        base["multiplier"] = 1.0
    elif pf == "fast":
        base["multiplier"] = max(1.2, float(base.get("multiplier") or 2.0) * 0.85)
        base["max_sec"] = max(5.0, float(base.get("max_sec") or 15.0) * 0.6)
    elif pf == "conservative":
        base["multiplier"] = max(1.8, float(base.get("multiplier") or 2.0) * 1.15)
        base["max_sec"] = max(10.0, float(base.get("max_sec") or 15.0) * 1.5)
    up = (p or "default").upper()
    try:
        v = os.getenv(f"QUENTIN_LISTENER_BACKOFF_{up}_INIT_SEC")
        if v:
            base["initial_sec"] = max(0.1, float(v))
    except Exception:
        pass
    try:
        v = os.getenv(f"QUENTIN_LISTENER_BACKOFF_{up}_MAX_SEC")
        if v:
            base["max_sec"] = max(1.0, float(v))
    except Exception:
        pass
    try:
        v = os.getenv(f"QUENTIN_LISTENER_BACKOFF_{up}_MULT")
        if v:
            base["multiplier"] = max(1.0, float(v))
    except Exception:
        pass
    try:
        v = os.getenv(f"QUENTIN_LISTENER_BACKOFF_{up}_RATE_LIMIT_FLOOR_SEC")
        if v:
            base["rate_limit_floor_sec"] = max(0.5, float(v))
    except Exception:
        pass
    if float(base.get("max_sec") or 0.0) < float(base.get("initial_sec") or 0.0):
        base["max_sec"] = float(base.get("initial_sec") or 0.5)
    return base


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)) or str(default))
    except Exception:
        return int(default)


class ChannelListenerManager:
    _instance: Optional["ChannelListenerManager"] = None

    def __new__(cls) -> "ChannelListenerManager":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._lock = threading.Lock()
            cls._instance._runtimes = {}
        return cls._instance

    def _build_adapter(self, platform: str, config: Dict[str, Any]) -> ChannelAdapter:
        p = str(platform or "").strip().lower()
        if p == "slack":
            from quentin.infra.channels.slack_adapter import SlackAdapter

            return SlackAdapter(app_token=str(config.get("app_token") or ""), bot_token=str(config.get("bot_token") or ""))
        if p == "discord":
            from quentin.infra.channels.discord_adapter import DiscordAdapter

            return DiscordAdapter(token=str(config.get("token") or ""))
        if p == "telegram":
            from quentin.infra.channels.telegram import TelegramAdapter

            return TelegramAdapter(token=str(config.get("token") or ""))
        raise ValueError(f"unsupported platform: {platform}")

    def start(
        self,
        platform: str,
        *,
        config: Dict[str, Any],
        on_message: Optional[Callable[[InboundMessage], Any]] = None,
    ) -> Dict[str, Any]:
        p = str(platform or "").strip().lower()
        if not p:
            return {"status": "error", "error": "platform required"}
        with self._lock:
            rt = self._runtimes.get(p)
            if rt and rt.status in {"running", "starting"}:
                return {"status": "ok", "platform": p, "already_running": True}

        try:
            adapter = self._build_adapter(p, config)
        except Exception as e:
            return {"status": "error", "platform": p, "error": str(e)}

        loop = asyncio.new_event_loop()
        runtime = ListenerRuntime(
            platform=p,
            adapter=adapter,
            loop=loop,
            thread=threading.Thread(),
            rate_limit_per_min=max(10, _env_int("QUENTIN_LISTENER_RATE_LIMIT_PER_MIN", 120)),
            backoff_profile=str(os.getenv("QUENTIN_LISTENER_BACKOFF_PROFILE", "exponential") or "exponential").strip().lower(),
        )
        runtime.backoff_policy = _resolve_backoff_policy(p, runtime.backoff_profile)

        async def _on_inbound(msg: InboundMessage) -> None:
            now = time.time()
            # Drop when platform ingress exceeds configured rate.
            while runtime.recent_arrivals and (now - runtime.recent_arrivals[0]) > 60.0:
                runtime.recent_arrivals.popleft()
            if len(runtime.recent_arrivals) >= int(runtime.rate_limit_per_min):
                runtime.dropped_count += 1
                return
            runtime.recent_arrivals.append(now)
            runtime.msg_seq += 1
            item = {
                "seq": int(runtime.msg_seq),
                "ts": now,
                "platform": p,
                "text": str(msg.text or ""),
                "sender_id": str(msg.sender_id or ""),
                "channel_id": str(msg.channel_id or p),
                "message_id": str(msg.message_id or ""),
                "metadata": dict(msg.metadata or {}),
            }
            runtime.messages.append(item)
            if len(runtime.messages) > 2000:
                runtime.messages = runtime.messages[-1000:]
            if on_message:
                try:
                    out = on_message(msg)
                    if asyncio.iscoroutine(out):
                        await out
                except Exception as e:
                    logger.warning("listener on_message callback failed: %s", e)

        adapter.set_on_message(_on_inbound)

        def _runner() -> None:
            asyncio.set_event_loop(loop)
            policy = dict(runtime.backoff_policy or {})
            backoff = max(0.1, float(policy.get("initial_sec") or 0.5))
            backoff_max = max(backoff, float(policy.get("max_sec") or 15.0))
            multiplier = max(1.0, float(policy.get("multiplier") or 2.0))
            rate_limit_floor = max(0.5, float(policy.get("rate_limit_floor_sec") or 4.0))
            try:
                while not runtime.stop_flag:
                    try:
                        loop.run_until_complete(adapter.start())
                        runtime.status = "running"
                        # Hold thread while adapter runs; if start returns unexpectedly,
                        # treat as disconnect and restart.
                        while not runtime.stop_flag:
                            time.sleep(0.2)
                        break
                    except Exception as e:
                        runtime.last_error = str(e)
                        runtime.status = "error"
                        runtime.restart_count += 1
                        reason = _classify_restart_reason(e)
                        runtime.last_restart_reason = reason
                        runtime.restart_reasons[reason] = int(runtime.restart_reasons.get(reason) or 0) + 1
                        logger.error("listener %s start failed: %s", p, e)
                        if runtime.stop_flag:
                            break
                        if reason == "rate_limit":
                            backoff = max(backoff, rate_limit_floor)
                        time.sleep(backoff)
                        if runtime.backoff_profile == "linear":
                            backoff = min(backoff_max, backoff + 0.5)
                        else:
                            backoff = min(backoff_max, backoff * multiplier)
            finally:
                try:
                    if loop.is_running():
                        loop.stop()
                except Exception:
                    pass
                try:
                    pending = asyncio.all_tasks(loop=loop)
                    for t in pending:
                        t.cancel()
                except Exception:
                    pass
                try:
                    loop.close()
                except Exception:
                    pass
                if runtime.status not in {"error", "stopped"}:
                    runtime.status = "stopped"

        th = threading.Thread(target=_runner, name=f"listener-{p}", daemon=True)
        runtime.thread = th
        with self._lock:
            self._runtimes[p] = runtime
        th.start()
        return {"status": "ok", "platform": p, "started": True}

    def stop(self, platform: str) -> Dict[str, Any]:
        p = str(platform or "").strip().lower()
        with self._lock:
            rt = self._runtimes.get(p)
        if not rt:
            return {"status": "ok", "platform": p, "stopped": False, "reason": "not_running"}

        async def _stop_adapter() -> None:
            try:
                await rt.adapter.stop()
            except Exception:
                pass

        rt.stop_flag = True
        try:
            if rt.loop.is_running() and (not rt.loop.is_closed()):
                fut = asyncio.run_coroutine_threadsafe(_stop_adapter(), rt.loop)
                fut.result(timeout=3.0)
        except Exception:
            pass
        try:
            rt.loop.call_soon_threadsafe(rt.loop.stop)
        except Exception:
            pass
        rt.status = "stopped"
        with self._lock:
            self._runtimes.pop(p, None)
        return {"status": "ok", "platform": p, "stopped": True}

    def status(self, platform: Optional[str] = None) -> Dict[str, Any]:
        with self._lock:
            if platform:
                rt = self._runtimes.get(str(platform).lower())
                rows = [rt] if rt else []
            else:
                rows = list(self._runtimes.values())
        items: List[Dict[str, Any]] = []
        for rt in rows:
            if not rt:
                continue
            items.append(
                {
                    "platform": rt.platform,
                    "status": rt.status,
                    "started_at": float(rt.started_at),
                    "uptime_sec": max(0, int(time.time() - rt.started_at)),
                    "message_count": len(rt.messages),
                    "latest_seq": int(rt.msg_seq),
                    "last_error": str(rt.last_error or ""),
                    "restart_count": int(rt.restart_count),
                    "last_restart_reason": str(rt.last_restart_reason or ""),
                    "restart_reasons": dict(rt.restart_reasons or {}),
                    "dropped_count": int(rt.dropped_count),
                    "rate_limit_per_min": int(rt.rate_limit_per_min),
                    "backoff_profile": str(rt.backoff_profile or "exponential"),
                    "backoff_policy": dict(rt.backoff_policy or {}),
                }
            )
        return {"status": "ok", "listeners": items, "count": len(items)}

    def poll(self, platform: str, *, from_seq: int = 0, limit: int = 100) -> Dict[str, Any]:
        p = str(platform or "").strip().lower()
        with self._lock:
            rt = self._runtimes.get(p)
        if not rt:
            return {"status": "ok", "platform": p, "events": [], "count": 0, "next_seq": int(from_seq), "latest_seq": 0}
        fs = max(0, int(from_seq or 0))
        lm = max(1, min(500, int(limit or 100)))
        events = [e for e in rt.messages if int(e.get("seq") or 0) > fs][:lm]
        next_seq = fs if not events else int(events[-1].get("seq") or fs)
        return {
            "status": "ok",
            "platform": p,
            "events": events,
            "count": len(events),
            "next_seq": next_seq,
            "latest_seq": int(rt.msg_seq),
        }


listener_manager = ChannelListenerManager()
