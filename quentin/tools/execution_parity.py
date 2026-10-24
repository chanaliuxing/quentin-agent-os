from __future__ import annotations

import asyncio
import hashlib
import inspect
import json
import os
import random
import re
import time
import urllib.request
import uuid
from datetime import datetime, timedelta, timezone
from ipaddress import ip_address
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

_THREAD_SUMMARY_TRIGGER = 40
_THREAD_KEEP_RECENT = 16
_THREAD_SUMMARY_MAX_CHARS = 2400
_THREAD_INTENT_CLASSIFIER_ENV = "QUENTIN_THREAD_INTENT_CLASSIFIER"
_THREAD_HISTORY_LIMIT_ENV = "QUENTIN_THREAD_HISTORY_LIMIT"
_THREAD_PLANNER_HISTORY_LIMIT_ENV = "QUENTIN_THREAD_PLANNER_HISTORY_LIMIT"
_LISTENER_DEDUPE_TTL_SEC = 3600
_LISTENER_MAX_RETRIES = 2


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)) or str(default))
    except Exception:
        return int(default)


def _stable_json(obj: Any) -> str:
    try:
        return json.dumps(obj, ensure_ascii=False, sort_keys=True)
    except Exception:
        return repr(obj)


def _short_hash(text: str) -> str:
    return hashlib.md5(str(text or "").encode("utf-8")).hexdigest()[:12]


def _repo_root_from_ctx(ctx: Any) -> Path:
    root = "."
    try:
        md = getattr(ctx, "metadata", {}) or {}
        root = str(md.get("repo_root") or ".")
    except Exception:
        root = "."
    return Path(root).resolve()


def _http_post_json(url: str, payload: Dict[str, Any], timeout: float = 15.0) -> Dict[str, Any]:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = resp.read().decode("utf-8", errors="ignore")
        return {"status_code": int(resp.status), "body": body[:4000]}


def _append_jsonl(path: Path, record: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def _load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _save_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # Atomic write to avoid partial/corrupt JSON when multiple writers exist.
    tmp = path.with_suffix(path.suffix + f".tmp.{uuid.uuid4().hex[:8]}")
    try:
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, path)
    finally:
        try:
            tmp.unlink(missing_ok=True)
        except Exception:
            pass


def _idempotency_store_path(root: Path, namespace: str) -> Path:
    safe_ns = re.sub(r"[^a-zA-Z0-9_.-]+", "_", str(namespace or "default")).strip("_") or "default"
    return root / "data" / "execution" / "idempotency" / f"{safe_ns}.json"


def _idempotency_is_seen(root: Path, *, namespace: str, key: str, ttl_sec: int = 3600) -> bool:
    k = str(key or "").strip()
    if not k:
        return False
    path = _idempotency_store_path(root, namespace)
    ttl = max(1, int(ttl_sec or 3600))
    now = _now_ts()
    try:
        from quentin.runtime.session_write_lock import acquire_session_write_lock

        hold = acquire_session_write_lock(session_file=path, timeout_ms=1200, stale_ms=30_000)
        try:
            raw = _load_json(path, {"keys": {}})
            if not isinstance(raw, dict):
                raw = {"keys": {}}
            keys = raw.get("keys") if isinstance(raw.get("keys"), dict) else {}
            purge_before = now - float(ttl)
            for item_k in list(keys.keys()):
                try:
                    if float(keys.get(item_k) or 0.0) < purge_before:
                        keys.pop(item_k, None)
                except Exception:
                    keys.pop(item_k, None)
            seen = k in keys
            raw["keys"] = keys
            _save_json(path, raw)
            return bool(seen)
        finally:
            hold["release"]()
    except Exception:
        raw = _load_json(path, {"keys": {}})
        keys = raw.get("keys") if isinstance(raw, dict) and isinstance(raw.get("keys"), dict) else {}
        purge_before = now - float(ttl)
        for item_k in list(keys.keys()):
            try:
                if float(keys.get(item_k) or 0.0) < purge_before:
                    keys.pop(item_k, None)
            except Exception:
                keys.pop(item_k, None)
        _save_json(path, {"keys": keys})
        return bool(k in keys)


def _idempotency_mark_seen(root: Path, *, namespace: str, key: str, ttl_sec: int = 3600) -> None:
    k = str(key or "").strip()
    if not k:
        return
    path = _idempotency_store_path(root, namespace)
    ttl = max(1, int(ttl_sec or 3600))
    now = _now_ts()
    try:
        from quentin.runtime.session_write_lock import acquire_session_write_lock

        hold = acquire_session_write_lock(session_file=path, timeout_ms=1200, stale_ms=30_000)
        try:
            raw = _load_json(path, {"keys": {}})
            if not isinstance(raw, dict):
                raw = {"keys": {}}
            keys = raw.get("keys") if isinstance(raw.get("keys"), dict) else {}
            purge_before = now - float(ttl)
            for item_k in list(keys.keys()):
                try:
                    if float(keys.get(item_k) or 0.0) < purge_before:
                        keys.pop(item_k, None)
                except Exception:
                    keys.pop(item_k, None)
            keys[k] = now
            raw["keys"] = keys
            _save_json(path, raw)
        finally:
            hold["release"]()
    except Exception:
        raw = _load_json(path, {"keys": {}})
        keys = raw.get("keys") if isinstance(raw, dict) and isinstance(raw.get("keys"), dict) else {}
        keys[k] = now
        _save_json(path, {"keys": keys})


def _now_ts() -> float:
    return float(time.time())


def _parse_cron_to_interval_seconds(expr: str) -> Optional[int]:
    text = str(expr or "").strip()
    if not text:
        return None
    lower = text.lower()
    if lower in {"@hourly", "@hour"}:
        return 3600
    if lower in {"@daily", "@day"}:
        return 86400
    if lower in {"@weekly", "@week"}:
        return 7 * 86400
    if lower in {"@monthly", "@month"}:
        return 30 * 86400
    if re.fullmatch(r"\d+[smhd]", text):
        n = int(text[:-1])
        unit = text[-1]
        mult = {"s": 1, "m": 60, "h": 3600, "d": 86400}[unit]
        return max(1, n * mult)
    parts = text.split()
    if len(parts) != 5:
        return None
    minute = parts[0]
    if minute.startswith("*/"):
        try:
            step = int(minute[2:])
            return max(60, step * 60)
        except Exception:
            return None
    if minute == "*":
        return 60
    if minute.isdigit():
        return 3600
    return None


_CRON_MONTHS = {
    "JAN": 1,
    "FEB": 2,
    "MAR": 3,
    "APR": 4,
    "MAY": 5,
    "JUN": 6,
    "JUL": 7,
    "AUG": 8,
    "SEP": 9,
    "OCT": 10,
    "NOV": 11,
    "DEC": 12,
}
_CRON_WEEKDAYS = {
    "SUN": 0,
    "MON": 1,
    "TUE": 2,
    "WED": 3,
    "THU": 4,
    "FRI": 5,
    "SAT": 6,
}
_SPECIAL_CRON = {
    "@yearly": "0 0 1 1 *",
    "@annually": "0 0 1 1 *",
    "@monthly": "0 0 1 * *",
    "@weekly": "0 0 * * 0",
    "@daily": "0 0 * * *",
    "@hourly": "0 * * * *",
}


def _parse_cron_field(
    field: str,
    *,
    min_v: int,
    max_v: int,
    name_map: Optional[Dict[str, int]] = None,
) -> Optional[Tuple[List[int], bool]]:
    text = str(field or "").strip()
    if not text:
        return None
    is_any = text == "*"

    def _tok(v: str) -> Optional[int]:
        t = str(v or "").strip().upper()
        if not t:
            return None
        if name_map and t in name_map:
            return int(name_map[t])
        try:
            return int(t)
        except Exception:
            return None

    vals: set[int] = set()
    for part in text.split(","):
        p = part.strip()
        if not p:
            return None
        if p == "*":
            vals.update(range(min_v, max_v + 1))
            continue
        if p.startswith("*/"):
            try:
                step = int(p[2:])
            except Exception:
                return None
            if step <= 0:
                return None
            vals.update(range(min_v, max_v + 1, step))
            continue
        if "-" in p:
            try:
                a, b = p.split("-", 1)
                start_v = _tok(a)
                end_v = _tok(b)
            except Exception:
                return None
            if start_v is None or end_v is None:
                return None
            start = int(start_v)
            end = int(end_v)
            if start > end:
                return None
            for v in range(start, end + 1):
                if min_v <= v <= max_v:
                    vals.add(v)
            continue
        v = _tok(p)
        if v is None:
            return None
        if not (min_v <= v <= max_v):
            return None
        vals.add(int(v))
    out = sorted(vals)
    if not out:
        return None
    return out, is_any


def _parse_cron_expr(expr: str) -> Optional[Dict[str, List[int]]]:
    raw = str(expr or "").strip()
    if not raw:
        return None
    lowered = raw.lower()
    if lowered in _SPECIAL_CRON:
        raw = _SPECIAL_CRON[lowered]
    parts = raw.split()
    if len(parts) != 5:
        return None
    mins_out = _parse_cron_field(parts[0], min_v=0, max_v=59)
    hrs_out = _parse_cron_field(parts[1], min_v=0, max_v=23)
    dom_out = _parse_cron_field(parts[2], min_v=1, max_v=31)
    mon_out = _parse_cron_field(parts[3], min_v=1, max_v=12, name_map=_CRON_MONTHS)
    # Weekday: accept 0-7 with 7==Sunday (cron convention).
    dow_out = _parse_cron_field(parts[4], min_v=0, max_v=7, name_map=_CRON_WEEKDAYS)
    if not all([mins_out, hrs_out, dom_out, mon_out, dow_out]):
        return None
    mins, _mins_any = mins_out
    hrs, _hrs_any = hrs_out
    dom, dom_any = dom_out
    mon, _mon_any = mon_out
    dow, dow_any = dow_out
    # Convert cron DOW (0/7=Sunday, 1=Monday, ..., 6=Saturday) to Python weekday()
    # (0=Monday, ..., 6=Sunday) so matching is correct.
    dow_norm: set[int] = set()
    for v in dow:
        iv = int(v)
        if iv == 7:
            iv = 0
        if iv == 0:
            py = 6
        else:
            py = iv - 1
        if 0 <= py <= 6:
            dow_norm.add(int(py))
    dow_norm = sorted(dow_norm)
    if not dow_norm:
        return None
    return {
        "minute": mins,
        "hour": hrs,
        "day": dom,
        "month": mon,
        "weekday": dow_norm,
        "_dom_any": dom_any,
        "_dow_any": dow_any,
    }


def _next_fire_from_cron(expr: str, *, now_ts: Optional[float] = None, max_scan_minutes: int = 60 * 24 * 32) -> Optional[float]:
    parsed = _parse_cron_expr(expr)
    if not parsed:
        return None
    now = datetime.fromtimestamp(float(now_ts or _now_ts()), tz=timezone.utc)
    probe = (now + timedelta(minutes=1)).replace(second=0, microsecond=0)
    for _ in range(max_scan_minutes):
        dom_any = bool(parsed.get("_dom_any"))
        dow_any = bool(parsed.get("_dow_any"))
        dom_match = probe.day in parsed["day"]
        dow_match = probe.weekday() in parsed["weekday"]
        if dom_any and dow_any:
            day_ok = True
        elif dom_any:
            day_ok = dow_match
        elif dow_any:
            day_ok = dom_match
        else:
            # Cron semantics: when both DOM and DOW are restricted, match either field.
            day_ok = dom_match or dow_match
        if (
            probe.minute in parsed["minute"]
            and probe.hour in parsed["hour"]
            and probe.month in parsed["month"]
            and day_ok
        ):
            return probe.timestamp()
        probe += timedelta(minutes=1)
    return None


def _next_n_fire_from_cron(expr: str, *, now_ts: Optional[float] = None, n: int = 5) -> List[float]:
    parsed = _parse_cron_expr(expr)
    if not parsed:
        return []
    target_n = max(0, int(n))
    if target_n == 0:
        return []
    now = datetime.fromtimestamp(float(now_ts or _now_ts()), tz=timezone.utc)
    probe = (now + timedelta(minutes=1)).replace(second=0, microsecond=0)
    out: List[float] = []
    max_scan_minutes = 60 * 24 * 62
    for _ in range(max_scan_minutes):
        dom_any = bool(parsed.get("_dom_any"))
        dow_any = bool(parsed.get("_dow_any"))
        dom_match = probe.day in parsed["day"]
        dow_match = probe.weekday() in parsed["weekday"]
        if dom_any and dow_any:
            day_ok = True
        elif dom_any:
            day_ok = dow_match
        elif dow_any:
            day_ok = dom_match
        else:
            day_ok = dom_match or dow_match
        if (
            probe.minute in parsed["minute"]
            and probe.hour in parsed["hour"]
            and probe.month in parsed["month"]
            and day_ok
        ):
            out.append(probe.timestamp())
            if len(out) >= target_n:
                break
        probe += timedelta(minutes=1)
    return out


def _send_with_webhook_or_stub(*, platform: str, text: str, webhook: str = "", dry_run: bool = False) -> Dict[str, Any]:
    ts = _now_ts()
    if dry_run or not webhook:
        return {
            "status": "ok",
            "platform": platform,
            "dry_run": True,
            "sent": False,
            "preview": text[:2000],
            "delivery_receipt": {
                "platform": platform,
                "sent": False,
                "mode": "dry_run",
                "ts": ts,
            },
        }
    if platform == "slack":
        payload = {"text": text}
    elif platform == "discord":
        payload = {"content": text}
    else:
        payload = {"text": text}
    res = _http_post_json(webhook, payload)
    return {
        "status": "ok",
        "platform": platform,
        "dry_run": False,
        "sent": True,
        "response": res,
        "delivery_receipt": {
            "platform": platform,
            "sent": True,
            "mode": "webhook",
            "ts": ts,
        },
    }


async def _send_via_adapter(platform: str, *, token: str, target_id: str, text: str) -> bool:
    try:
        if platform == "slack":
            from quentin.infra.channels.slack_adapter import SlackAdapter

            adapter = SlackAdapter(app_token="", bot_token=token)
            await adapter.send_text(target_id=target_id, text=text)
            return True
        if platform == "discord":
            from quentin.infra.channels.discord_adapter import DiscordAdapter

            adapter = DiscordAdapter(token=token)
            await adapter.send_text(target_id=target_id, text=text)
            return True
        if platform == "telegram":
            from quentin.infra.channels.telegram import TelegramAdapter

            adapter = TelegramAdapter(token=token)
            await adapter.send_text(target_id=target_id, text=text)
            return True
        if platform == "whatsapp":
            from quentin.infra.channels.whatsapp_adapter import WhatsAppAdapter

            phone_number_id = str(os.getenv("WHATSAPP_PHONE_NUMBER_ID") or "")
            if not phone_number_id:
                return False
            adapter = WhatsAppAdapter(token=token, phone_number_id=phone_number_id)
            await adapter.send_text(target_id=target_id, text=text)
            return True
    except Exception:
        return False
    return False


async def slack_actions(req: Dict[str, Any], ctx: Any = None) -> Dict[str, Any]:
    ta = _thread_action("slack", req, ctx)
    if ta is not None:
        return ta
    text = str(req.get("text") or "")
    webhook = str(req.get("webhook_url") or os.getenv("SLACK_WEBHOOK_URL") or "")
    dry_run = bool(req.get("dry_run", False))
    token = str(req.get("bot_token") or os.getenv("SLACK_BOT_TOKEN") or "")
    target_id = str(req.get("target_id") or req.get("channel_id") or "")
    if not dry_run and token and target_id:
        sent = await _send_via_adapter("slack", token=token, target_id=target_id, text=text)
        if sent:
            thread_id = _normalize_thread_id(req)
            _thread_append(_repo_root_from_ctx(ctx), "slack", thread_id=thread_id, role="agent", text=text)
            return {
                "status": "ok",
                "platform": "slack",
                "dry_run": False,
                "sent": True,
                "via": "adapter",
                "thread_id": thread_id,
                "delivery_receipt": {
                    "platform": "slack",
                    "sent": True,
                    "mode": "adapter",
                    "target_id": target_id,
                    "ts": _now_ts(),
                },
            }
    res = _send_with_webhook_or_stub(platform="slack", text=text, webhook=webhook, dry_run=dry_run)
    if res.get("status") == "ok":
        thread_id = _normalize_thread_id(req)
        _thread_append(_repo_root_from_ctx(ctx), "slack", thread_id=thread_id, role="agent", text=text)
        res["thread_id"] = thread_id
    return res


async def discord_actions(req: Dict[str, Any], ctx: Any = None) -> Dict[str, Any]:
    ta = _thread_action("discord", req, ctx)
    if ta is not None:
        return ta
    text = str(req.get("text") or "")
    webhook = str(req.get("webhook_url") or os.getenv("DISCORD_WEBHOOK_URL") or "")
    dry_run = bool(req.get("dry_run", False))
    token = str(req.get("bot_token") or os.getenv("DISCORD_BOT_TOKEN") or "")
    target_id = str(req.get("target_id") or req.get("channel_id") or "")
    if not dry_run and token and target_id:
        sent = await _send_via_adapter("discord", token=token, target_id=target_id, text=text)
        if sent:
            thread_id = _normalize_thread_id(req)
            _thread_append(_repo_root_from_ctx(ctx), "discord", thread_id=thread_id, role="agent", text=text)
            return {
                "status": "ok",
                "platform": "discord",
                "dry_run": False,
                "sent": True,
                "via": "adapter",
                "thread_id": thread_id,
                "delivery_receipt": {
                    "platform": "discord",
                    "sent": True,
                    "mode": "adapter",
                    "target_id": target_id,
                    "ts": _now_ts(),
                },
            }
    res = _send_with_webhook_or_stub(platform="discord", text=text, webhook=webhook, dry_run=dry_run)
    if res.get("status") == "ok":
        thread_id = _normalize_thread_id(req)
        _thread_append(_repo_root_from_ctx(ctx), "discord", thread_id=thread_id, role="agent", text=text)
        res["thread_id"] = thread_id
    return res


async def telegram_actions(req: Dict[str, Any], ctx: Any = None) -> Dict[str, Any]:
    ta = _thread_action("telegram", req, ctx)
    if ta is not None:
        return ta
    text = str(req.get("text") or "")
    dry_run = bool(req.get("dry_run", False))
    token = str(req.get("bot_token") or os.getenv("TELEGRAM_BOT_TOKEN") or "")
    chat_id = str(req.get("chat_id") or os.getenv("TELEGRAM_CHAT_ID") or "")
    if not dry_run and token and chat_id:
        sent = await _send_via_adapter("telegram", token=token, target_id=chat_id, text=text)
        if sent:
            thread_id = _normalize_thread_id(req)
            _thread_append(_repo_root_from_ctx(ctx), "telegram", thread_id=thread_id, role="agent", text=text)
            return {
                "status": "ok",
                "platform": "telegram",
                "dry_run": False,
                "sent": True,
                "via": "adapter",
                "thread_id": thread_id,
                "delivery_receipt": {
                    "platform": "telegram",
                    "sent": True,
                    "mode": "adapter",
                    "target_id": chat_id,
                    "ts": _now_ts(),
                },
            }
    if dry_run or not (token and chat_id):
        thread_id = _normalize_thread_id(req)
        _thread_append(_repo_root_from_ctx(ctx), "telegram", thread_id=thread_id, role="agent", text=text)
        return {
            "status": "ok",
            "platform": "telegram",
            "dry_run": True,
            "sent": False,
            "thread_id": thread_id,
            "preview": text[:2000],
            "delivery_receipt": {"platform": "telegram", "sent": False, "mode": "dry_run", "ts": _now_ts()},
        }
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    res = _http_post_json(url, {"chat_id": chat_id, "text": text})
    thread_id = _normalize_thread_id(req)
    _thread_append(_repo_root_from_ctx(ctx), "telegram", thread_id=thread_id, role="agent", text=text)
    return {
        "status": "ok",
        "platform": "telegram",
        "dry_run": False,
        "sent": True,
        "thread_id": thread_id,
        "response": res,
        "delivery_receipt": {"platform": "telegram", "sent": True, "mode": "http_api", "target_id": chat_id, "ts": _now_ts()},
    }


async def whatsapp_actions(req: Dict[str, Any], ctx: Any = None) -> Dict[str, Any]:
    ta = _thread_action("whatsapp", req, ctx)
    if ta is not None:
        return ta
    text = str(req.get("text") or "")
    dry_run = bool(req.get("dry_run", True))
    endpoint = str(req.get("endpoint") or os.getenv("WHATSAPP_ENDPOINT") or "")
    token = str(req.get("token") or os.getenv("WHATSAPP_TOKEN") or "")
    target_id = str(req.get("target_id") or req.get("to") or "")
    if not dry_run and token and target_id:
        sent = await _send_via_adapter("whatsapp", token=token, target_id=target_id, text=text)
        if sent:
            thread_id = _normalize_thread_id(req)
            _thread_append(_repo_root_from_ctx(ctx), "whatsapp", thread_id=thread_id, role="agent", text=text)
            return {
                "status": "ok",
                "platform": "whatsapp",
                "dry_run": False,
                "sent": True,
                "via": "adapter",
                "thread_id": thread_id,
                "delivery_receipt": {
                    "platform": "whatsapp",
                    "sent": True,
                    "mode": "adapter",
                    "target_id": target_id,
                    "ts": _now_ts(),
                },
            }
    if dry_run or not (endpoint and token):
        thread_id = _normalize_thread_id(req)
        _thread_append(_repo_root_from_ctx(ctx), "whatsapp", thread_id=thread_id, role="agent", text=text)
        return {
            "status": "ok",
            "platform": "whatsapp",
            "dry_run": True,
            "sent": False,
            "thread_id": thread_id,
            "preview": text[:2000],
            "delivery_receipt": {"platform": "whatsapp", "sent": False, "mode": "dry_run", "ts": _now_ts()},
        }
    payload = {"text": text, "token": token}
    res = _http_post_json(endpoint, payload)
    thread_id = _normalize_thread_id(req)
    _thread_append(_repo_root_from_ctx(ctx), "whatsapp", thread_id=thread_id, role="agent", text=text)
    return {
        "status": "ok",
        "platform": "whatsapp",
        "dry_run": False,
        "sent": True,
        "thread_id": thread_id,
        "response": res,
        "delivery_receipt": {"platform": "whatsapp", "sent": True, "mode": "http_api", "target_id": target_id, "ts": _now_ts()},
    }


def _message_tool_action(raw_action: str) -> str:
    action = str(raw_action or "send").strip().lower()
    aliases = {
        "post": "send",
        "publish": "send",
        "reply": "send",
        "message": "send",
        "fetch": "fetch_thread",
        "thread": "fetch_thread",
        "threads": "list_threads",
        "list": "list_threads",
        "receive": "ingest",
        "ingest_event": "ingest",
        "message_edit": "edit",
        "edited": "edit",
        "message_delete": "delete",
        "deleted": "delete",
        "add_reaction": "react",
        "reaction": "react",
    }
    return aliases.get(action, action)


def _message_tool_prepare_req(platform: str, req: Dict[str, Any]) -> Dict[str, Any]:
    p = str(platform or "").strip().lower()
    payload: Dict[str, Any] = dict(req or {})
    payload["platform"] = p
    action = _message_tool_action(payload.get("action") or "send")
    payload["action"] = action
    if "text" not in payload and payload.get("message") is not None:
        payload["text"] = str(payload.get("message") or "")

    if p in {"slack", "discord"}:
        channel_id = str(payload.get("channel_id") or payload.get("target_id") or "").strip()
        if channel_id:
            payload.setdefault("channel_id", channel_id)
            payload.setdefault("target_id", channel_id)
            if not str(payload.get("thread_id") or "").strip():
                payload["thread_id"] = f"{p}:{channel_id}"
    elif p == "telegram":
        chat_id = str(payload.get("chat_id") or payload.get("target_id") or payload.get("channel_id") or "").strip()
        if chat_id:
            payload.setdefault("chat_id", chat_id)
            if not str(payload.get("thread_id") or "").strip():
                payload["thread_id"] = f"telegram:{chat_id}"
    elif p == "whatsapp":
        to = str(payload.get("to") or payload.get("target_id") or payload.get("chat_id") or payload.get("channel_id") or "").strip()
        if to:
            payload.setdefault("to", to)
            payload.setdefault("target_id", to)
            if not str(payload.get("thread_id") or "").strip():
                payload["thread_id"] = f"whatsapp:{to}"
    return payload


async def message_tool(req: Dict[str, Any], ctx: Any = None) -> Dict[str, Any]:
    platform = str(req.get("platform") or "").strip().lower()
    if platform not in {"discord", "slack", "telegram", "whatsapp"}:
        return {"status": "error", "error": "platform required: discord|slack|telegram|whatsapp"}

    payload = _message_tool_prepare_req(platform, req)
    action = str(payload.get("action") or "send").strip().lower()
    root = _repo_root_from_ctx(ctx)
    idem = str(payload.get("idempotency_key") or payload.get("idempotencyKey") or "").strip()
    idem_ttl_sec = int(payload.get("idempotency_ttl_sec") or 3600)
    mutating = action in {"send", "ingest", "edit", "delete", "react"}
    idem_scope = f"message_tool:{platform}:{action}"
    if mutating and idem and _idempotency_is_seen(root, namespace=idem_scope, key=idem, ttl_sec=idem_ttl_sec):
        return {
            "status": "ok",
            "platform": platform,
            "tool": "message.tool",
            "action": action,
            "deduped": True,
            "idempotency_key": idem,
            "routed_to": f"{platform}.actions" if action in {"send", "ingest"} else "thread_store",
        }
    platform_handlers = {
        "discord": discord_actions,
        "slack": slack_actions,
        "telegram": telegram_actions,
        "whatsapp": whatsapp_actions,
    }
    handler = platform_handlers[platform]

    if action in {"send", "ingest", "fetch_thread", "list_threads"}:
        out = await handler(payload, ctx)
        if isinstance(out, dict):
            out.setdefault("platform", platform)
            out.setdefault("tool", "message.tool")
            out.setdefault("routed_to", f"{platform}.actions")
            if mutating and idem and str(out.get("status") or "") == "ok":
                _idempotency_mark_seen(root, namespace=idem_scope, key=idem, ttl_sec=idem_ttl_sec)
        return out

    thread_id = _normalize_thread_id(payload)
    message_id = str(payload.get("message_id") or payload.get("external_message_id") or "").strip()
    meta = dict(payload.get("meta") or {})
    user_id = str(payload.get("user_id") or "agent")

    if action in {"edit", "delete"}:
        if message_id and "external_message_id" not in meta:
            meta["external_message_id"] = message_id
        event_kind = "edit" if action == "edit" else "delete"
        out = _thread_apply_event(
            root,
            platform,
            thread_id=thread_id,
            event_kind=event_kind,
            text=str(payload.get("text") or ""),
            user_id=user_id,
            message_id=message_id,
            meta=meta,
        )
        out.setdefault("platform", platform)
        out.setdefault("tool", "message.tool")
        out.setdefault("routed_to", "thread_store")
        if idem and str(out.get("status") or "") == "ok":
            _idempotency_mark_seen(root, namespace=idem_scope, key=idem, ttl_sec=idem_ttl_sec)
        return out

    if action == "react":
        emoji = str(payload.get("emoji") or payload.get("reaction") or "").strip()
        if not emoji:
            return {"status": "error", "error": "emoji/reaction required for react"}
        _thread_append(
            root,
            platform,
            thread_id=thread_id,
            role="system",
            text=f"reaction {emoji}",
            user_id=user_id,
            meta={**meta, "event_kind": "reaction", "reaction": emoji, "target_message_id": message_id},
        )
        if idem:
            _idempotency_mark_seen(root, namespace=idem_scope, key=idem, ttl_sec=idem_ttl_sec)
        return {
            "status": "ok",
            "platform": platform,
            "thread_id": thread_id,
            "event": "react",
            "applied": True,
            "tool": "message.tool",
            "routed_to": "thread_store",
        }

    return {"status": "error", "error": f"unsupported action: {action}"}


def gateway_tool(req: Dict[str, Any], ctx: Any = None) -> Dict[str, Any]:
    action = str(req.get("action") or "status").strip().lower()
    root = _repo_root_from_ctx(ctx)
    if action in {"status", "providers", "list_providers"}:
        try:
            from quentin.config.feature_flags import feature_flags
            from quentin.infra.channels.gateway_server import gateway

            providers = sorted([str(k) for k in getattr(gateway, "_providers", {}).keys()])
            active_connections = len(list(getattr(gateway, "_active_connections", []) or []))
            return {
                "status": "ok",
                "gateway_enabled": bool(getattr(feature_flags, "gateway_v1", False)),
                "provider_count": len(providers),
                "providers": providers,
                "active_connections": active_connections,
            }
        except Exception as e:
            return {"status": "error", "error": str(e)}

    if action == "inbound":
        platform = str(req.get("platform") or req.get("channel") or "").strip().lower()
        if platform not in {"discord", "slack", "telegram", "whatsapp"}:
            return {"status": "error", "error": "platform/channel required: discord|slack|telegram|whatsapp"}
        text = str(req.get("text") or "").strip()
        if not text:
            return {"status": "error", "error": "text required"}
        idem = str(req.get("idempotency_key") or req.get("idempotencyKey") or "").strip()
        idem_ttl_sec = int(req.get("idempotency_ttl_sec") or 3600)
        if idem and _idempotency_is_seen(root, namespace=f"gateway_tool:{platform}:inbound", key=idem, ttl_sec=idem_ttl_sec):
            return {"status": "accepted", "channel": platform, "deduped": True, "idempotency_key": idem}
        metadata = dict(req.get("metadata") or {})
        sender_id = str(req.get("sender_id") or req.get("user_id") or "user")
        message_id = str(req.get("message_id") or "") or f"gw_{uuid.uuid4().hex[:10]}"
        res = channels_listener_tool(
            {
                "action": "inject",
                "platform": platform,
                "text": text,
                "sender_id": sender_id,
                "message_id": message_id,
                "metadata": metadata,
                "auto_reply": bool(req.get("auto_reply", False)),
                "auto_reply_mode": str(req.get("auto_reply_mode") or "template"),
                "auto_reply_template": str(req.get("auto_reply_template") or "ACK:{text}"),
                "auto_reply_send": bool(req.get("auto_reply_send", False)),
            },
            ctx,
        )
        status = "accepted" if str(res.get("status") or "") == "ok" else "error"
        if idem and status == "accepted":
            _idempotency_mark_seen(root, namespace=f"gateway_tool:{platform}:inbound", key=idem, ttl_sec=idem_ttl_sec)
        return {"status": status, "channel": platform, "result": res}

    if action == "outbound":
        platform = str(req.get("platform") or req.get("channel") or "").strip().lower()
        if platform not in {"discord", "slack", "telegram", "whatsapp"}:
            return {"status": "error", "error": "platform/channel required: discord|slack|telegram|whatsapp"}
        text = str(req.get("text") or "").strip()
        if not text:
            return {"status": "error", "error": "text required"}
        idem = str(req.get("idempotency_key") or req.get("idempotencyKey") or "").strip()
        idem_ttl_sec = int(req.get("idempotency_ttl_sec") or 3600)
        if idem and _idempotency_is_seen(root, namespace=f"gateway_tool:{platform}:outbound", key=idem, ttl_sec=idem_ttl_sec):
            return {"status": "ok", "platform": platform, "tool": "gateway.tool", "deduped": True, "idempotency_key": idem}
        payload = dict(req or {})
        payload.setdefault("platform", platform)
        payload["action"] = "send"
        if "dry_run" not in payload:
            payload["dry_run"] = True
        out = asyncio.run(message_tool(payload, ctx))
        if isinstance(out, dict):
            out["tool"] = "gateway.tool"
            if idem and str(out.get("status") or "") == "ok":
                _idempotency_mark_seen(root, namespace=f"gateway_tool:{platform}:outbound", key=idem, ttl_sec=idem_ttl_sec)
        return out

    return {"status": "error", "error": f"unknown action: {action}"}


def _agent_step_handlers() -> Dict[str, Any]:
    return {
        "message.tool": message_tool,
        "discord.actions": discord_actions,
        "slack.actions": slack_actions,
        "telegram.actions": telegram_actions,
        "whatsapp.actions": whatsapp_actions,
        "channels.listener": channels_listener_tool_async,
        "gateway.tool": gateway_tool,
        "cron.tool": cron_tool,
        "session.status": session_status_tool,
        "sessions.announce_target": sessions_announce_target,
        "sessions.list": sessions_list_tool,
        "sessions.history": sessions_history_tool,
        "sessions.send": sessions_send_tool,
        "sessions.spawn": sessions_spawn_tool,
        "web.readability": web_readability_tool,
        "web.fetch": web_fetch_tool,
        "web.search": web_search_tool,
        "memory.search": memory_search_tool,
        "memory.get": memory_get_tool,
        "image.tool": image_tool,
        "tts.tool": tts_tool,
        "canvas.tool": canvas_tool,
        "agents.list": agents_list_tool,
        "nodes.tool": nodes_tool,
    }


def agent_step_tool(req: Dict[str, Any], ctx: Any = None) -> Dict[str, Any]:
    action = str(req.get("action") or "execute").strip().lower()
    if action != "execute":
        return {"status": "error", "error": f"unknown action: {action}"}

    step = req.get("step") if isinstance(req.get("step"), dict) else {}
    tool_name = str(req.get("tool") or step.get("tool") or step.get("name") or "").strip()
    args = req.get("args") if isinstance(req.get("args"), dict) else step.get("args")
    if not isinstance(args, dict):
        args = {}
    if not tool_name:
        return {"status": "error", "error": "tool required (or step.tool/step.name)"}
    root = _repo_root_from_ctx(ctx)
    handlers = _agent_step_handlers()
    handler = handlers.get(tool_name)
    if handler is None:
        return {"status": "error", "error": f"unsupported tool: {tool_name}"}

    max_retries = max(0, min(5, int(req.get("max_retries") or 0)))
    attempts: List[Dict[str, Any]] = []
    last_result: Dict[str, Any] = {}
    success = False
    started = _now_ts()
    for idx in range(max_retries + 1):
        t0 = time.perf_counter()
        try:
            if inspect.iscoroutinefunction(handler):
                out = asyncio.run(handler(args, ctx))
            else:
                out = handler(args, ctx)
            latency_ms = (time.perf_counter() - t0) * 1000.0
            out_obj = out if isinstance(out, dict) else {"result": out}
            status = str(out_obj.get("status") or "")
            ok = status == "ok" or status == "accepted"
            attempts.append({"index": idx + 1, "ok": bool(ok), "latency_ms": latency_ms, "status": status})
            last_result = dict(out_obj)
            if ok:
                success = True
                break
        except Exception as e:
            latency_ms = (time.perf_counter() - t0) * 1000.0
            attempts.append({"index": idx + 1, "ok": False, "latency_ms": latency_ms, "error": str(e)})
            last_result = {"status": "error", "error": str(e)}
    finished = _now_ts()
    correction_intensity = "low" if success else ("medium" if len(attempts) <= 2 else "high")
    kind = "none" if success else ("tool_execution_error" if str(last_result.get("status") or "") == "error" else "logical_path_error")
    rec = {
        "ts": finished,
        "tool": tool_name,
        "attempts": len(attempts),
        "success": success,
        "error_kind": kind,
        "correction_intensity": correction_intensity,
        "duration_ms": max(0.0, (finished - started) * 1000.0),
    }
    try:
        _append_jsonl(root / "data" / "agent_step_runs.jsonl", rec)
    except Exception:
        pass
    return {
        "status": "ok" if success else "error",
        "tool": tool_name,
        "attempt_count": len(attempts),
        "attempts": attempts,
        "result": last_result,
        "error_kind": kind,
        "correction_intensity": correction_intensity,
    }


def _cron_next_fire(item: Dict[str, Any], now: float) -> Optional[float]:
    stored = item.get("next_fire_ts")
    if isinstance(stored, (int, float)) and float(stored) > 0.0:
        return float(stored)
    cron_expr = str(item.get("cron") or "")
    next_fire = _next_fire_from_cron(cron_expr, now_ts=now) if cron_expr else None
    if next_fire is None and int(item.get("interval") or 0) > 0:
        next_fire = float(item.get("last_run") or 0.0) + float(item.get("interval") or 0.0)
    jitter_sec = int(item.get("jitter_sec") or 0)
    if jitter_sec > 0 and isinstance(next_fire, (int, float)):
        next_fire = float(next_fire) + min(jitter_sec, 300)
    return next_fire


def _cron_next_after(item: Dict[str, Any], *, after_ts: float) -> Optional[float]:
    cron_expr = str(item.get("cron") or "")
    nf = _next_fire_from_cron(cron_expr, now_ts=float(after_ts)) if cron_expr else None
    if nf is None:
        interval = int(item.get("interval") or 0)
        nf = (float(after_ts) + float(interval)) if interval > 0 else None
    jitter_sec = int(item.get("jitter_sec") or 0)
    if jitter_sec > 0 and isinstance(nf, (int, float)):
        nf = float(nf) + min(jitter_sec, 300)
    return nf


def _cron_enqueue_task(
    root: Path,
    *,
    name: str,
    item: Dict[str, Any],
    now: float,
    fire_ts: Optional[float] = None,
) -> Dict[str, Any]:
    from quentin.runtime.task_queue import TaskQueue, TaskQueueItem

    queue = TaskQueue(repo_root=str(root))
    metadata = dict(item.get("metadata") or {})
    metadata.update({"source": "cron.tool", "cron_task_name": name, "cron_ts": now})
    if isinstance(fire_ts, (int, float)):
        metadata["cron_fire_ts"] = float(fire_ts)
    qitem = TaskQueueItem.new(
        input_text=str(item.get("input") or ""),
        domain=str(item.get("domain") or "maintenance"),
        environment=str(item.get("environment") or "sandbox"),
        session_id=str(item.get("session_id") or "cron"),
        priority=int(item.get("priority") or 0),
        metadata=metadata,
    )
    queue.append(qitem)
    return {"task_id": qitem.task_id, "input_text": qitem.input_text, "domain": qitem.domain, "environment": qitem.environment}


def cron_tool(req: Dict[str, Any], ctx: Any = None) -> Dict[str, Any]:
    action = str(req.get("action") or "list").strip().lower()
    root = _repo_root_from_ctx(ctx)
    db = root / "data" / "cron_tasks.json"
    runs_db = root / "data" / "cron_runs.jsonl"
    tasks = _load_json(db, {})
    if not isinstance(tasks, dict):
        tasks = {}

    def _append_run(rec: Dict[str, Any]) -> None:
        try:
            _append_jsonl(runs_db, rec)
        except Exception:
            pass

    if action == "runs":
        name = str(req.get("name") or "").strip()
        limit = max(1, min(500, int(req.get("limit") or 50)))
        rows: List[Dict[str, Any]] = []
        if runs_db.exists():
            try:
                lines = runs_db.read_text(encoding="utf-8", errors="ignore").splitlines()
                for line in reversed(lines):
                    if not line.strip():
                        continue
                    try:
                        obj = json.loads(line)
                    except Exception:
                        continue
                    if not isinstance(obj, dict):
                        continue
                    if name and str(obj.get("name") or "") != name:
                        continue
                    rows.append(obj)
                    if len(rows) >= limit:
                        break
            except Exception:
                rows = []
        return {"status": "ok", "count": len(rows), "runs": rows, "name": name or None}

    if action == "list":
        now = _now_ts()
        enriched: Dict[str, Any] = {}
        for name, t in (tasks or {}).items():
            if not isinstance(t, dict):
                continue
            item = dict(t)
            next_fire = _cron_next_fire(item, now)
            misfire_policy = str(item.get("misfire_policy") or "skip")
            if isinstance(next_fire, (int, float)) and next_fire <= now and misfire_policy == "skip":
                cron_expr = str(item.get("cron") or "")
                next_fire = _next_fire_from_cron(cron_expr, now_ts=now + 60) if cron_expr else (now + max(1.0, float(item.get("interval") or 60)))
            item["next_fire_ts"] = next_fire
            item["next_fire_in_sec"] = (next_fire - now) if isinstance(next_fire, (int, float)) else None
            enriched[str(name)] = item
        return {"status": "ok", "tasks": enriched}

    if action == "status":
        now = _now_ts()
        due_names: List[str] = []
        for name, t in tasks.items():
            if not isinstance(t, dict):
                continue
            nf = _cron_next_fire(t, now)
            if isinstance(nf, (int, float)) and float(nf) <= now:
                due_names.append(str(name))
        return {"status": "ok", "task_count": len(tasks), "due_count": len(due_names), "due_names": due_names[:200]}

    if action == "preview":
        expr = str(req.get("cron") or req.get("interval") or "").strip()
        n = int(req.get("count") or 5)
        now = _now_ts()
        times = _next_n_fire_from_cron(expr, now_ts=now, n=n)
        if not times:
            interval = _parse_cron_to_interval_seconds(expr)
            if interval is None:
                return {"status": "error", "error": "invalid cron/interval expression"}
            times = [now + interval * (i + 1) for i in range(max(1, n))]
        return {"status": "ok", "cron": expr, "next_fire_times": times, "count": len(times)}

    if action == "remove":
        name = str(req.get("name") or "").strip()
        if name and name in tasks:
            tasks.pop(name, None)
            _save_json(db, tasks)
        return {"status": "ok", "removed": name, "tasks": tasks}

    if action == "schedule":
        name = str(req.get("name") or "").strip()
        task_input = str(req.get("task_input") or "").strip()
        expr = str(req.get("cron") or req.get("interval") or "").strip()
        interval = _parse_cron_to_interval_seconds(expr)
        cron_parsed = _parse_cron_expr(expr)
        if not name or not task_input or (interval is None and cron_parsed is None):
            return {"status": "error", "error": "invalid schedule params: require name/task_input/(cron or interval)"}
        now = _now_ts()
        start_immediately = bool(req.get("start_immediately", True))
        next_fire = _next_fire_from_cron(expr, now_ts=now) if cron_parsed else (now if start_immediately else (now + float(interval or 0)))
        jitter_sec = int(req.get("jitter_sec") or 0)
        misfire_policy = str(req.get("misfire_policy") or "skip").strip().lower()
        if misfire_policy not in {"skip", "catch_up"}:
            misfire_policy = "skip"
        if jitter_sec > 0 and isinstance(next_fire, (int, float)):
            next_fire = float(next_fire) + min(jitter_sec, 300)
        tasks[name] = {
            "interval": int(interval or 0),
            "input": task_input,
            "last_run": 0,
            "metadata": dict(req.get("metadata") or {}),
            "domain": str(req.get("domain") or "maintenance"),
            "environment": str(req.get("environment") or "sandbox"),
            "session_id": str(req.get("session_id") or "cron"),
            "priority": int(req.get("priority") or 0),
            "cron": expr,
            "next_fire_ts": next_fire,
            "jitter_sec": jitter_sec,
            "misfire_policy": misfire_policy,
        }
        _save_json(db, tasks)
        return {"status": "ok", "scheduled": name, "interval_seconds": int(interval or 0), "task": tasks[name]}

    if action == "run_due":
        now = _now_ts()
        dry_run = bool(req.get("dry_run", False))
        max_tasks = max(1, min(500, int(req.get("max_tasks") or 50)))
        max_catch_up = max(1, min(200, int(req.get("max_catch_up") or 20)))
        due: List[Tuple[str, Dict[str, Any], float]] = []
        for name, raw in tasks.items():
            if not isinstance(raw, dict):
                continue
            item = dict(raw)
            # Prefer stored next_fire_ts when present; recompute as fallback.
            next_fire = item.get("next_fire_ts")
            if not isinstance(next_fire, (int, float)):
                next_fire = _cron_next_fire(item, now)
            misfire_policy = str(item.get("misfire_policy") or "skip").strip().lower()
            if isinstance(next_fire, (int, float)) and float(next_fire) <= now:
                if misfire_policy == "catch_up":
                    due.append((str(name), item, float(next_fire)))
                else:
                    due.append((str(name), item, now))
        due = sorted(due, key=lambda x: float(x[2]))[:max_tasks]
        if dry_run:
            return {
                "status": "ok",
                "dry_run": True,
                "due_count": len(due),
                "due_names": [x[0] for x in due],
            }
        enqueued: List[Dict[str, Any]] = []
        for name, item, fire_ts in due:
            misfire_policy = str(item.get("misfire_policy") or "skip").strip().lower()
            fires: List[float] = []
            if misfire_policy == "catch_up":
                probe = float(fire_ts)
                # Enqueue each missed fire up to now, bounded to avoid runaway.
                while probe <= now and len(fires) < max_catch_up and (len(enqueued) + len(fires)) < max_tasks:
                    fires.append(float(probe))
                    nxt = _cron_next_after(item, after_ts=float(probe))
                    if nxt is None:
                        break
                    if float(nxt) <= float(probe):
                        break
                    probe = float(nxt)
            else:
                fires = [float(fire_ts)]

            last_fire = float(item.get("last_run") or 0.0)
            for fts in fires:
                rec = _cron_enqueue_task(root, name=name, item=item, now=now, fire_ts=float(fts))
                enqueued.append({"name": name, "fire_ts": float(fts), **rec})
                last_fire = float(fts)
                _append_run(
                    {
                        "ts": now,
                        "name": name,
                        "fire_ts": float(fts),
                        "task_id": str(rec.get("task_id") or ""),
                        "mode": "catch_up" if misfire_policy == "catch_up" else "normal",
                        "session_id": str(item.get("session_id") or "cron"),
                        "domain": str(item.get("domain") or "maintenance"),
                        "environment": str(item.get("environment") or "sandbox"),
                    }
                )
            # Advance last_run and next_fire_ts based on the last enqueued fire.
            if fires:
                item["last_run"] = float(last_fire)
                nf = _cron_next_after(item, after_ts=float(last_fire))
                item["next_fire_ts"] = nf if isinstance(nf, (int, float)) else None
            else:
                item["last_run"] = now
                item["next_fire_ts"] = _cron_next_fire(item, now)
            tasks[name] = item
        _save_json(db, tasks)
        return {"status": "ok", "enqueued_count": len(enqueued), "enqueued": enqueued}

    return {"status": "error", "error": f"unknown action: {action}"}


def session_status_tool(req: Dict[str, Any], ctx: Any = None) -> Dict[str, Any]:
    root = _repo_root_from_ctx(ctx)
    lock_dir = root / "data" / "runtime" / "session_locks"
    subagent_file = root / "data" / "subagent_status.json"
    cron_file = root / "data" / "cron_tasks.json"
    active_sessions: List[str] = []
    if lock_dir.exists():
        for p in sorted(lock_dir.glob("*.lock")):
            active_sessions.append(p.stem)
    subagents = _load_json(subagent_file, {})
    cron_tasks = _load_json(cron_file, {})
    announce_file = root / "data" / "session_announcements.jsonl"
    now = _now_ts()
    due_cron = 0
    if isinstance(cron_tasks, dict):
        for _, t in cron_tasks.items():
            if not isinstance(t, dict):
                continue
            next_fire = t.get("next_fire_ts")
            if isinstance(next_fire, (int, float)) and float(next_fire) <= now:
                due_cron += 1
    health = "healthy"
    if len(active_sessions) > 20 or due_cron > 5:
        health = "warning"
    if len(active_sessions) > 50 or due_cron > 20:
        health = "critical"
    listener_status: Dict[str, Any] = {"status": "ok", "listeners": [], "count": 0}
    try:
        from quentin.infra.channels.listener_manager import listener_manager

        listener_status = listener_manager.status()
    except Exception:
        listener_status = {"status": "error", "listeners": [], "count": 0}
    if int(listener_status.get("count") or 0) > 3 and health == "healthy":
        health = "warning"
    listener_restart_reasons: Dict[str, int] = {}
    listener_rate_limits: Dict[str, int] = {}
    listener_backoff_profiles: Dict[str, str] = {}
    for li in list(listener_status.get("listeners") or []):
        if not isinstance(li, dict):
            continue
        pname = str(li.get("platform") or "")
        if pname:
            listener_rate_limits[pname] = int(li.get("rate_limit_per_min") or 0)
            listener_backoff_profiles[pname] = str(li.get("backoff_profile") or "exponential")
        for rk, rv in dict(li.get("restart_reasons") or {}).items():
            key = str(rk or "").strip() or "unknown"
            try:
                listener_restart_reasons[key] = listener_restart_reasons.get(key, 0) + int(rv or 0)
            except Exception:
                continue
    listener_state = _listener_state_load(root)
    dead_letters = list(listener_state.get("dead_letters") or [])
    try:
        from quentin.runtime.task_queue import TaskQueue

        q = TaskQueue(repo_root=str(root))
        q_items = q.load_all(limit=5000)
        queue_pending = sum(1 for it in q_items if str(getattr(it, "status", "")) == "pending")
    except Exception:
        queue_pending = 0
    canvas_file = root / "data" / "canvas_components.json"
    canvas_ack_timeout_sec = max(5, int(req.get("canvas_ack_timeout_sec") or _env_int("QUENTIN_CANVAS_ACK_TIMEOUT_SEC", 120)))
    canvas_active_components = 0
    canvas_ack_pending_count = 0
    canvas_ack_pending: List[Dict[str, Any]] = []
    canvas_data = _load_json(canvas_file, {"components": {}})
    if isinstance(canvas_data, dict):
        comps = canvas_data.get("components")
        if isinstance(comps, dict):
            now_ts = _now_ts()
            for cid, node in comps.items():
                if not isinstance(node, dict):
                    continue
                st = str(node.get("status") or "active").strip().lower()
                if st not in {"active", "pending", "running"}:
                    continue
                canvas_active_components += 1
                last_ack = node.get("last_ack") if isinstance(node.get("last_ack"), dict) else {}
                last_ack_ts = float((last_ack or {}).get("ts") or 0.0)
                updated_at = float(node.get("updated_at") or 0.0)
                ref_ts = max(last_ack_ts, updated_at)
                age_sec = max(0, int(now_ts - ref_ts))
                if ref_ts <= 0.0 or age_sec >= canvas_ack_timeout_sec:
                    canvas_ack_pending_count += 1
                    canvas_ack_pending.append(
                        {
                            "component_id": str(node.get("component_id") or cid),
                            "status": st,
                            "age_sec": age_sec,
                        }
                    )
    if canvas_ack_pending_count > 0 and health == "healthy":
        health = "warning"
    handoff_edges: List[Dict[str, Any]] = []
    handoff_map: Dict[str, Dict[str, Any]] = {}
    source_set: set[str] = set()
    target_set: set[str] = set()
    if announce_file.exists():
        try:
            for line in announce_file.read_text(encoding="utf-8", errors="ignore").splitlines()[-500:]:
                try:
                    rec = json.loads(line)
                except Exception:
                    continue
                src = str(rec.get("source_session_id") or "").strip()
                dst = str(rec.get("target_session_id") or "").strip()
                if not (src and dst):
                    continue
                source_set.add(src)
                target_set.add(dst)
                key = f"{src}->{dst}"
                node = handoff_map.get(key) or {"source": src, "target": dst, "count": 0, "last_ts": 0.0}
                node["count"] = int(node["count"]) + 1
                try:
                    node["last_ts"] = max(float(node["last_ts"]), float(rec.get("ts") or 0.0))
                except Exception:
                    pass
                handoff_map[key] = node
        except Exception:
            handoff_map = {}
    handoff_edges = sorted(handoff_map.values(), key=lambda x: (-int(x.get("count") or 0), -float(x.get("last_ts") or 0.0)))[:50]
    dangling_handoff_targets = sorted([t for t in target_set if t not in source_set])[:200]
    graph: Dict[str, List[str]] = {}
    for e in handoff_edges:
        s = str(e.get("source") or "")
        t = str(e.get("target") or "")
        if not (s and t):
            continue
        graph.setdefault(s, [])
        if t not in graph[s]:
            graph[s].append(t)
    longest_chain_length = 0
    cycle_nodes: set[str] = set()

    def _dfs(node: str, path: List[str]) -> None:
        nonlocal longest_chain_length
        longest_chain_length = max(longest_chain_length, len(path))
        for nxt in graph.get(node, []):
            if nxt in path:
                cycle_nodes.update(path[path.index(nxt):] + [nxt])
                continue
            _dfs(nxt, path + [nxt])

    for n in list(graph.keys()):
        _dfs(n, [n])
    return {
        "status": "ok",
        "health": health,
        "active_session_count": len(active_sessions),
        "active_sessions": active_sessions[:200],
        "subagent_count": len(subagents) if isinstance(subagents, dict) else 0,
        "subagents": subagents if isinstance(subagents, dict) else {},
        "cron_due_count": due_cron,
        "cron_task_count": len(cron_tasks) if isinstance(cron_tasks, dict) else 0,
        "listener_count": int(listener_status.get("count") or 0),
        "listeners": list(listener_status.get("listeners") or [])[:50],
        "listener_restart_reasons": listener_restart_reasons,
        "listener_rate_limits": listener_rate_limits,
        "listener_backoff_profiles": listener_backoff_profiles,
        "listener_dead_letter_count": len(dead_letters),
        "queue_pending_count": int(queue_pending),
        "canvas_ack_timeout_sec": int(canvas_ack_timeout_sec),
        "canvas_active_component_count": int(canvas_active_components),
        "canvas_ack_pending_count": int(canvas_ack_pending_count),
        "canvas_ack_pending": sorted(canvas_ack_pending, key=lambda x: -int(x.get("age_sec") or 0))[:100],
        "handoff_edges": handoff_edges,
        "dangling_handoff_targets": dangling_handoff_targets,
        "handoff_longest_chain_length": longest_chain_length,
        "handoff_cycle_nodes": sorted(list(cycle_nodes))[:200],
    }


def sessions_announce_target(req: Dict[str, Any], ctx: Any = None) -> Dict[str, Any]:
    root = _repo_root_from_ctx(ctx)
    action = str(req.get("action") or "announce").strip().lower()
    path = root / "data" / "session_announcements.jsonl"
    relay_file = root / "data" / "session_relay_queue.json"
    queue = _load_json(relay_file, [])
    if not isinstance(queue, list):
        queue = []

    if action in {"list", "peek"}:
        dst = str(req.get("target_session_id") or "").strip()
        limit = max(1, min(200, int(req.get("limit") or 50)))
        rows = [r for r in queue if isinstance(r, dict)]
        if dst:
            rows = [r for r in rows if str(r.get("target_session_id") or "") == dst]
        rows = sorted(rows, key=lambda x: float(x.get("ts") or 0.0), reverse=True)[:limit]
        return {"status": "ok", "items": rows, "count": len(rows), "target_session_id": dst or None}

    if action in {"consume", "ack"}:
        dst = str(req.get("target_session_id") or "").strip()
        if not dst:
            return {"status": "error", "error": "target_session_id is required for consume"}
        limit = max(1, min(200, int(req.get("limit") or 20)))
        consumed: List[Dict[str, Any]] = []
        kept: List[Dict[str, Any]] = []
        for item in queue:
            if not isinstance(item, dict):
                continue
            if str(item.get("target_session_id") or "") == dst and len(consumed) < limit:
                consumed.append(item)
            else:
                kept.append(item)
        _save_json(relay_file, kept)
        return {"status": "ok", "consumed": consumed, "count": len(consumed), "remaining": len(kept)}

    src = str(req.get("source_session_id") or "global")
    dst = str(req.get("target_session_id") or "global")
    target = str(req.get("target") or "").strip()
    if not target:
        return {"status": "error", "error": "target is required"}
    rec = {
        "id": f"handoff_{int(_now_ts() * 1000)}_{hashlib.md5((src + '->' + dst + ':' + target).encode('utf-8')).hexdigest()[:8]}",
        "ts": _now_ts(),
        "source_session_id": src,
        "target_session_id": dst,
        "target": target,
        "meta": dict(req.get("meta") or {}),
    }
    _append_jsonl(path, rec)
    queue.append(rec)
    if len(queue) > 2000:
        queue = queue[-1000:]
    _save_json(relay_file, queue)
    return {"status": "ok", "recorded": True, "path": str(path), "record": rec, "queued": True, "queue_len": len(queue)}


def sessions_list_tool(req: Dict[str, Any], ctx: Any = None) -> Dict[str, Any]:
    """
    OpenClaw-style sessions list, backed by local runtime artifacts:
    - `data/runtime/session_locks/*.lock` for active sessions
    - `data/system_events/*.jsonl` for pending system events (via EventStoreBackend)
    - `data/tasks/queue.jsonl` for queued tasks
    - `data/subagent_status.json` for spawned subagent runs
    """
    root = _repo_root_from_ctx(ctx)
    limit = max(1, min(500, int(req.get("limit") or 200)))

    lock_dir = root / "data" / "runtime" / "session_locks"
    active: Dict[str, Dict[str, Any]] = {}
    now = _now_ts()
    if lock_dir.exists():
        for p in sorted(lock_dir.glob("*.lock")):
            sid = str(p.stem or "").strip()
            if not sid:
                continue
            try:
                mtime = float(p.stat().st_mtime)
            except Exception:
                mtime = 0.0
            active[sid] = {"active": True, "lock_path": str(p), "lock_age_sec": int(max(0.0, now - mtime))}

    # Pending system event sessions.
    event_sessions: List[str] = []
    try:
        from quentin.runtime.event_store import build_event_store_backend

        be = build_event_store_backend(repo_root=root)
        event_sessions = list(be.list_sessions() or [])
    except Exception:
        event_sessions = []

    # Task queue sessions.
    task_meta: Dict[str, Dict[str, Any]] = {}
    try:
        from quentin.runtime.task_queue import TaskQueue

        q = TaskQueue(repo_root=str(root))
        items = q.load_all(limit=5000)
        for it in items:
            sid = str(getattr(it, "session_id", "") or "").strip()
            if not sid:
                continue
            node = task_meta.get(sid) or {"pending": 0, "claimed": 0, "done": 0, "failed": 0, "last_created_at": ""}
            st = str(getattr(it, "status", "") or "pending")
            if st in node:
                node[st] = int(node.get(st) or 0) + 1
            created = str(getattr(it, "created_at", "") or "")
            if created and (not node.get("last_created_at") or created > str(node.get("last_created_at") or "")):
                node["last_created_at"] = created
            task_meta[sid] = node
    except Exception:
        task_meta = {}

    # Subagent registry sessions.
    subagent_file = root / "data" / "subagent_status.json"
    subagents = _load_json(subagent_file, {})
    sub_sessions: Dict[str, Any] = {}
    if isinstance(subagents, dict):
        sub_sessions = dict(subagents)

    # Merge all known sessions.
    all_ids = set(active.keys()) | set(event_sessions) | set(task_meta.keys()) | set(sub_sessions.keys())
    sessions: List[Dict[str, Any]] = []
    for sid in sorted(all_ids):
        node: Dict[str, Any] = {"session_id": sid}
        node.update(active.get(sid) or {"active": False})
        if sid in task_meta:
            node["tasks"] = dict(task_meta[sid])
        if sid in sub_sessions and isinstance(sub_sessions.get(sid), dict):
            node["subagent"] = dict(sub_sessions.get(sid) or {})
        if sid in event_sessions:
            node["has_pending_system_events"] = True
        sessions.append(node)

    def _activity_key(s: Dict[str, Any]) -> Tuple[int, str, int]:
        act = 1 if bool(s.get("active")) else 0
        last = ""
        t = s.get("tasks")
        if isinstance(t, dict):
            last = str(t.get("last_created_at") or "")
        lock_age = int(s.get("lock_age_sec") or 0)
        # active first, then most recent task (desc), then newest lock (smaller age).
        return (-act, last, lock_age)

    sessions.sort(key=_activity_key, reverse=True)
    return {"status": "ok", "count": len(sessions), "sessions": sessions[:limit]}


def sessions_history_tool(req: Dict[str, Any], ctx: Any = None) -> Dict[str, Any]:
    root = _repo_root_from_ctx(ctx)
    session_id = str(req.get("session_id") or req.get("sessionId") or "").strip()
    if not session_id:
        return {"status": "error", "error": "session_id required"}
    limit = max(1, min(500, int(req.get("limit") or 100)))

    # 1) Pending system events (peek).
    system_events: List[Dict[str, Any]] = []
    try:
        from quentin.runtime.event_store import build_event_store_backend

        be = build_event_store_backend(repo_root=root)
        system_events = list(be.peek_events(session_id, limit=min(200, limit)) or [])
    except Exception:
        system_events = []

    # 2) Task queue items (recent).
    tasks: List[Dict[str, Any]] = []
    try:
        from quentin.runtime.task_queue import TaskQueue

        q = TaskQueue(repo_root=str(root))
        items = q.load_all(limit=5000)
        for it in reversed(items):
            if str(getattr(it, "session_id", "") or "") != session_id:
                continue
            tasks.append(it.to_dict() if hasattr(it, "to_dict") else {})
            if len(tasks) >= limit:
                break
    except Exception:
        tasks = []

    # 3) Handoff announcements (recent).
    announcements: List[Dict[str, Any]] = []
    path = root / "data" / "session_announcements.jsonl"
    if path.exists():
        try:
            lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()[-2000:]
            for line in reversed(lines):
                if not line.strip():
                    continue
                try:
                    rec = json.loads(line)
                except Exception:
                    continue
                if not isinstance(rec, dict):
                    continue
                src = str(rec.get("source_session_id") or "")
                dst = str(rec.get("target_session_id") or "")
                if session_id not in {src, dst}:
                    continue
                announcements.append(rec)
                if len(announcements) >= min(200, limit):
                    break
        except Exception:
            announcements = []

    return {
        "status": "ok",
        "session_id": session_id,
        "system_events_peek": system_events,
        "task_queue_recent": tasks,
        "announcements_recent": announcements,
    }


def sessions_send_tool(req: Dict[str, Any], ctx: Any = None) -> Dict[str, Any]:
    """
    OpenClaw-style sessions send:
    - mode=system_event: enqueue into EventStoreBackend
    - mode=task: enqueue into TaskQueue
    Supports idempotency_key to dedupe sends.
    """
    root = _repo_root_from_ctx(ctx)
    session_id = str(req.get("session_id") or req.get("sessionId") or "").strip()
    text = str(req.get("text") or req.get("message") or req.get("input") or "").strip()
    if not session_id:
        return {"status": "error", "error": "session_id required"}
    if not text:
        return {"status": "error", "error": "text required"}
    mode = str(req.get("mode") or req.get("kind") or "system_event").strip().lower()
    idem = str(req.get("idempotency_key") or req.get("idempotencyKey") or "").strip()

    dedupe_path = root / "data" / "sessions_send_dedupe.json"
    ttl_sec = int(req.get("dedupe_ttl_sec") or 3600)

    def _dedupe_seen(key: str) -> bool:
        if not key:
            return False
        now = _now_ts()
        try:
            from quentin.runtime.session_write_lock import acquire_session_write_lock

            hold = acquire_session_write_lock(session_file=dedupe_path, timeout_ms=1200, stale_ms=30_000)
            try:
                db = _load_json(dedupe_path, {"keys": {}})
                if not isinstance(db, dict):
                    db = {"keys": {}}
                keys = db.get("keys")
                if not isinstance(keys, dict):
                    keys = {}
                # purge
                for k in list(keys.keys()):
                    try:
                        if float(keys.get(k) or 0.0) < (now - ttl_sec):
                            keys.pop(k, None)
                    except Exception:
                        keys.pop(k, None)
                if key in keys:
                    db["keys"] = keys
                    _save_json(dedupe_path, db)
                    return True
                keys[key] = now
                db["keys"] = keys
                _save_json(dedupe_path, db)
                return False
            finally:
                hold["release"]()
        except Exception:
            return False

    if idem and _dedupe_seen(f"{session_id}:{idem}"):
        return {"status": "ok", "deduped": True, "session_id": session_id, "idempotency_key": idem}

    if mode in {"task", "task_queue", "queue"}:
        from quentin.runtime.task_queue import TaskQueue, TaskQueueItem

        q = TaskQueue(repo_root=str(root))
        item = TaskQueueItem.new(
            input_text=text,
            domain=str(req.get("domain") or "core"),
            environment=str(req.get("environment") or "sandbox"),
            session_id=session_id,
            priority=int(req.get("priority") or 0),
            metadata=dict(req.get("metadata") or {"source": "sessions.send"}),
        )
        q.append(item)
        return {"status": "ok", "mode": "task_queue", "session_id": session_id, "task_id": item.task_id, "deduped": False}

    # Default: system_event.
    try:
        from quentin.runtime.event_store import build_event_store_backend

        be = build_event_store_backend(repo_root=root)
        be.enqueue_event(
            {
                "session_id": session_id,
                "kind": "system_event",
                "text": text,
                "meta": dict(req.get("meta") or req.get("metadata") or {}),
            }
        )
        return {"status": "ok", "mode": "system_event", "session_id": session_id, "enqueued": True, "deduped": False}
    except Exception as e:
        return {"status": "error", "error": f"failed to enqueue system_event: {e}", "session_id": session_id}


def sessions_spawn_tool(req: Dict[str, Any], ctx: Any = None) -> Dict[str, Any]:
    """
    Minimal "spawn" for Taylor: create a new isolated session_id and enqueue a first task.
    (This matches the runtime model: a daemon/worker will pick the task up.)
    """
    root = _repo_root_from_ctx(ctx)
    parent = ""
    try:
        md = getattr(ctx, "metadata", {}) or {}
        parent = str(md.get("session_id") or "")
    except Exception:
        parent = ""
    label = str(req.get("label") or "spawn").strip() or "spawn"
    session_id = str(req.get("session_id") or "").strip() or f"isolated:{uuid.uuid4().hex[:12]}"
    text = str(req.get("text") or req.get("task") or req.get("message") or "").strip()
    if not text:
        return {"status": "error", "error": "text required"}
    from quentin.runtime.task_queue import TaskQueue, TaskQueueItem

    q = TaskQueue(repo_root=str(root))
    item = TaskQueueItem.new(
        input_text=text,
        domain=str(req.get("domain") or "core"),
        environment=str(req.get("environment") or "sandbox"),
        session_id=session_id,
        priority=int(req.get("priority") or 0),
        metadata={
            "source": "sessions.spawn",
            "label": label,
            "parent_session_id": parent or None,
        },
    )
    q.append(item)
    return {"status": "ok", "session_id": session_id, "task_id": item.task_id, "label": label}


def _memory_allowed_roots(root: Path) -> List[Path]:
    # Keep this conservative; it is a *tool* and must not become an arbitrary file reader.
    candidates = [
        root / "MEMORY.md",
        root / "memory",
        root / "docs",
        root / "data" / "memory",
    ]
    out: List[Path] = []
    for p in candidates:
        try:
            out.append(p.resolve())
        except Exception:
            continue
    return out


def _is_under(path: Path, base: Path) -> bool:
    try:
        path = path.resolve()
        base = base.resolve()
        return str(path).startswith(str(base) + os.sep) or path == base
    except Exception:
        return False


def memory_search_tool(req: Dict[str, Any], ctx: Any = None) -> Dict[str, Any]:
    """
    OpenClaw-style memory_search parity (lightweight, file-based).
    Searches MEMORY.md + memory/*.md + docs/*.md for a query and returns best snippets.
    """
    root = _repo_root_from_ctx(ctx)
    query = str(req.get("query") or "").strip()
    if not query:
        return {"status": "ok", "query": query, "results": []}
    max_results = max(1, min(20, int(req.get("max_results") or req.get("maxResults") or 5)))
    min_score = float(req.get("min_score") or req.get("minScore") or 0.0)

    q = query.lower()
    allowed = _memory_allowed_roots(root)
    paths: List[Path] = []
    # Enumerate.
    for base in allowed:
        if base.is_file() and base.exists():
            paths.append(base)
            continue
        if base.is_dir() and base.exists():
            for p in sorted(base.rglob("*.md")):
                paths.append(p)
    results: List[Dict[str, Any]] = []
    for p in paths:
        try:
            rp = p.resolve()
        except Exception:
            continue
        if not any(_is_under(rp, b) for b in allowed):
            continue
        try:
            text = rp.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        if not text.strip():
            continue
        lines = text.splitlines()
        hits: List[int] = []
        for i, ln in enumerate(lines):
            if q in ln.lower():
                hits.append(i)
                if len(hits) >= 8:
                    break
        if not hits:
            continue
        first = hits[0]
        lo = max(0, first - 3)
        hi = min(len(lines), first + 6)
        snippet = "\n".join(lines[lo:hi]).strip()
        # score: hit count + weak recency bonus.
        try:
            mtime = float(rp.stat().st_mtime)
        except Exception:
            mtime = 0.0
        age = max(0.0, _now_ts() - mtime) if mtime > 0 else 0.0
        recency = 1.0 / (1.0 + (age / (3600.0 * 24.0 * 7.0)))  # ~1 week half-life
        score = float(len(hits)) + (0.25 * recency)
        if score < min_score:
            continue
        results.append(
            {
                "path": str(rp.relative_to(root) if _is_under(rp, root) else rp),
                "score": round(score, 4),
                "from_line": lo + 1,
                "to_line": hi,
                "snippet": snippet[:1200],
            }
        )
    results.sort(key=lambda r: float(r.get("score") or 0.0), reverse=True)
    return {"status": "ok", "query": query, "results": results[:max_results], "provider": "file_grep"}


def memory_get_tool(req: Dict[str, Any], ctx: Any = None) -> Dict[str, Any]:
    """
    Safe snippet read from MEMORY.md/memory/docs (allowlisted).
    """
    root = _repo_root_from_ctx(ctx)
    rel = str(req.get("path") or "").strip()
    if not rel:
        return {"status": "error", "error": "path required"}
    from_line = int(req.get("from") or req.get("from_line") or 1)
    lines_n = int(req.get("lines") or 80)
    from_line = max(1, from_line)
    lines_n = max(1, min(400, lines_n))
    allowed = _memory_allowed_roots(root)
    p = (root / rel).resolve()
    if not any(_is_under(p, b) for b in allowed):
        return {"status": "error", "error": "path not allowlisted"}
    if not p.exists() or not p.is_file():
        return {"status": "error", "error": "file not found"}
    text = p.read_text(encoding="utf-8", errors="ignore")
    rows = text.splitlines()
    lo = min(len(rows), from_line - 1)
    hi = min(len(rows), lo + lines_n)
    out = "\n".join(rows[lo:hi])
    return {"status": "ok", "path": rel, "from": from_line, "lines": lines_n, "text": out}


def _strip_html_noise(html: str) -> str:
    text = re.sub(r"(?is)<script.*?>.*?</script>", " ", html)
    text = re.sub(r"(?is)<style.*?>.*?</style>", " ", text)
    text = re.sub(r"(?is)<noscript.*?>.*?</noscript>", " ", text)
    # Generic readability-ish boilerplate stripping.
    text = re.sub(r"(?is)<(header|nav|footer|aside|form|svg|canvas|iframe)\b[^>]*>.*?</\1>", " ", text)
    # Role-based wrappers (common in SPA layouts).
    text = re.sub(r"(?is)<div[^>]*(role=\"(?:navigation|banner|contentinfo)\"|aria-label=\"[^\"]*(?:Navigation|Menu|Header|Footer)[^\"]*\")[^>]*>.*?</div>", " ", text)
    # Common comment/response blocks.
    text = re.sub(r"(?is)<(div|section)[^>]*(id|class)=\"[^\"]*(?:comment|comments|responses|reply|replies)[^\"]*\"[^>]*>.*?</\1>", " ", text)
    # Consent / cookie banners.
    text = re.sub(r"(?is)<(div|section)[^>]*(id|class)=\"[^\"]*(?:cookie|consent|gdpr|banner)[^\"]*\"[^>]*>.*?</\1>", " ", text)
    text = re.sub(r"(?is)<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _readability_diff_metrics(*, original_html: str, patched_html: str, clean_text: str) -> Dict[str, Any]:
    src = str(original_html or "")
    patched = str(patched_html or "")
    clean = str(clean_text or "")
    src_len = len(src)
    patched_len = len(patched)
    clean_len = len(clean)
    src_tags = len(re.findall(r"(?is)<[^>]+>", src))
    patched_tags = len(re.findall(r"(?is)<[^>]+>", patched))
    src_words = len(re.findall(r"[A-Za-z0-9_]+", src))
    clean_words = len(re.findall(r"[A-Za-z0-9_]+", clean))
    removed_chars = max(0, src_len - patched_len)
    return {
        "source_chars": src_len,
        "patched_chars": patched_len,
        "clean_chars": clean_len,
        "removed_chars": removed_chars,
        "removed_char_ratio": round((removed_chars / max(1, src_len)), 4),
        "clean_text_ratio_vs_source": round((clean_len / max(1, src_len)), 4),
        "tag_count_before": src_tags,
        "tag_count_after_patch": patched_tags,
        "tag_reduction_ratio": round(((src_tags - patched_tags) / max(1, src_tags)), 4),
        "word_count_before": src_words,
        "word_count_after": clean_words,
        "content_gain_ratio": round((clean_words / max(1, src_words)), 4),
    }


def _detect_site(url: str) -> str:
    try:
        host = str(urlparse(url).netloc or "").lower()
    except Exception:
        host = ""
    if "stackoverflow.com" in host or "stackexchange.com" in host:
        return "stackoverflow"
    if "github.com" in host:
        return "github"
    if "medium.com" in host:
        return "medium"
    if "reddit.com" in host:
        return "reddit"
    if "dev.to" in host:
        return "devto"
    if "nytimes.com" in host:
        return "nytimes"
    if "substack.com" in host:
        return "substack"
    if host.endswith("wikipedia.org") or ".wikipedia.org" in host:
        return "wikipedia"
    if "arxiv.org" in host:
        return "arxiv"
    if "news.ycombinator.com" in host:
        return "hackernews"
    return "generic"


def _apply_site_patch(url: str, html: str) -> Tuple[str, str, Dict[str, Any]]:
    site = _detect_site(url)
    text = str(html or "")
    removed = 0
    from quentin.tools.web_patch_rules import get_site_patch

    patch = get_site_patch(site)
    patterns = list(patch.get("patterns") or [])
    rules = list(patch.get("rules") or [])
    for p in patterns:
        text2, count = re.subn(p, " ", text)
        text = text2
        removed += int(count or 0)
    return site, text, {"site": site, "removed_blocks": removed, "rules": rules}


def _safe_emit_ui(event_type: str, payload: Dict[str, Any]) -> None:
    try:
        import asyncio
        from quentin.infra.events.environment_bus import environment_bus

        asyncio.get_running_loop()
        environment_bus.emit(event_type, payload)
    except Exception:
        return


def _generate_planner_reply(
    *,
    text: str,
    platform: str,
    thread_id: str,
    thread_history: Optional[List[Dict[str, Any]]] = None,
    thread_summary: str = "",
    ctx: Any = None,
    fallback_template: str = "收到: {text}",
) -> Dict[str, Any]:
    user_text = str(text or "").strip()
    if not user_text:
        reply = fallback_template.replace("{text}", "").replace("{sender_id}", "")
        return {"status": "ok", "mode": "template_fallback", "reply": reply}
    try:
        from quentin.bootstrap.container import Container
        from quentin.cognitive.loop import CognitiveTask

        history = list(thread_history or [])[-8:]
        context_lines: List[str] = []
        for msg in history:
            if not isinstance(msg, dict):
                continue
            role = str(msg.get("role") or "unknown")
            t = str(msg.get("text") or "").strip()
            if not t:
                continue
            context_lines.append(f"[{role}] {t[:280]}")
        context_block = ""
        summary_text = str(thread_summary or "").strip()
        if summary_text:
            context_block += f"{summary_text[:1200]}\n\n"
        if context_lines:
            context_block = "Conversation context:\n" + "\n".join(context_lines[-8:]) + "\n\n"
            if summary_text:
                context_block = f"{summary_text[:1200]}\n\n" + context_block

        container = Container()
        loop = container.cognitive_loop
        task = CognitiveTask(
            input_text=f"{context_block}Latest user message:\n{user_text}"[:5000],
            task_id=f"channel_{uuid.uuid4().hex[:10]}",
            domain="communication",
            environment="runtime",
            metadata={
                "source": "channels.listener.auto_reply",
                "platform": str(platform or ""),
                "thread_id": str(thread_id or ""),
                "history_count": len(history),
            },
        )
        result = loop.run_task(task)
        reply = str(getattr(result, "final_output", "") or "").strip()
        if not reply:
            reply = fallback_template.replace("{text}", user_text[:1000]).replace("{sender_id}", "")
            return {"status": "ok", "mode": "planner_empty_fallback", "reply": reply}
        return {"status": "ok", "mode": "planner", "reply": reply[:4000]}
    except Exception as e:
        reply = fallback_template.replace("{text}", user_text[:1000]).replace("{sender_id}", "")
        return {"status": "ok", "mode": "planner_error_fallback", "reply": reply, "error": str(e)}


def _thread_store_path(root: Path, platform: str) -> Path:
    return root / "data" / "channels" / f"{platform}_threads.json"


def _normalize_thread_id(req: Dict[str, Any]) -> str:
    thread_id = str(req.get("thread_id") or req.get("conversation_id") or req.get("channel_thread_id") or "").strip()
    return thread_id or "default"


def _thread_id_from_inbound(platform: str, metadata: Dict[str, Any]) -> str:
    md = dict(metadata or {})
    p = str(platform or "").strip().lower()
    if p == "discord":
        channel_id = str(md.get("channel_id") or "").strip()
        thread_id = str(md.get("thread_id") or "").strip()
        if thread_id:
            return f"discord:{channel_id}:thread:{thread_id}" if channel_id else f"discord:thread:{thread_id}"
        return f"discord:{channel_id}" if channel_id else "discord:default"
    if p == "slack":
        channel_id = str(md.get("channel_id") or "").strip()
        thread_ts = str(md.get("thread_ts") or md.get("ts") or "").strip()
        if thread_ts:
            return f"slack:{channel_id}:thread:{thread_ts}" if channel_id else f"slack:thread:{thread_ts}"
        return f"slack:{channel_id}" if channel_id else "slack:default"
    if p == "telegram":
        chat_id = str(md.get("chat_id") or "").strip()
        topic_id = str(md.get("message_thread_id") or "").strip()
        if topic_id:
            return f"telegram:{chat_id}:topic:{topic_id}" if chat_id else f"telegram:topic:{topic_id}"
        return f"telegram:{chat_id}" if chat_id else "telegram:default"
    raw = str(md.get("thread_id") or md.get("channel_id") or md.get("chat_id") or "").strip()
    return raw or f"{p or 'unknown'}:default"


def _thread_store_load(root: Path, platform: str) -> Dict[str, Any]:
    data = _load_json(_thread_store_path(root, platform), {"threads": {}})
    if not isinstance(data, dict):
        data = {"threads": {}}
    if not isinstance(data.get("threads"), dict):
        data["threads"] = {}
    return data


def _thread_store_save(root: Path, platform: str, data: Dict[str, Any]) -> None:
    path = _thread_store_path(root, platform)
    try:
        from quentin.runtime.session_write_lock import acquire_session_write_lock

        hold = acquire_session_write_lock(session_file=path, timeout_ms=2000, stale_ms=30_000)
        try:
            _save_json(path, data)
        finally:
            hold["release"]()
    except Exception:
        _save_json(path, data)


def _summarize_thread_messages(messages: List[Dict[str, Any]], *, max_items: int = 24) -> str:
    lines: List[str] = []
    for msg in list(messages)[-max_items:]:
        if not isinstance(msg, dict):
            continue
        role = str(msg.get("role") or "unknown")
        text = str(msg.get("text") or "").strip()
        if not text:
            continue
        lines.append(f"- {role}: {text[:140]}")
    if not lines:
        return ""
    return "Thread summary:\n" + "\n".join(lines)


def _classify_summary_intent_rule(text: str) -> str:
    t = str(text or "").strip().lower()
    if not t:
        return "statement"
    if "?" in t or any(k in t for k in ["why", "how", "what", "when", "where", "which", "can you"]):
        return "question"
    if any(k in t for k in ["error", "fail", "exception", "timeout", "crash", "bug", "traceback"]):
        return "failure"
    if any(k in t for k in ["done", "fixed", "resolved", "updated", "merged", "completed"]):
        return "done"
    if any(k in t for k in ["plan", "next", "todo", "step", "action"]):
        return "plan"
    return "statement"


def _classify_summary_intent_rules_v2(text: str) -> str:
    t = str(text or "").strip().lower()
    if not t:
        return "statement"
    if any(k in t for k in ["error", "fail", "exception", "timeout", "crash", "bug", "traceback"]):
        return "report_issue"
    if "?" in t or any(k in t for k in ["why", "how", "what", "when", "where", "which", "can you"]):
        return "request_info"
    if any(k in t for k in ["please", "could you", "should", "change", "update", "modify", "refactor", "rewrite", "add", "remove"]):
        return "request_change"
    if any(k in t for k in ["plan", "next", "todo", "step", "action"]):
        return "plan"
    if any(k in t for k in ["done", "fixed", "resolved", "updated", "merged", "completed"]):
        return "status_update"
    return "statement"


def _classify_summary_intent(text: str) -> str:
    mode = str(os.getenv(_THREAD_INTENT_CLASSIFIER_ENV, "rule") or "rule").strip().lower()
    # Pluggable interface: keep this switch stable for future model-based classifiers.
    if mode in {"", "rule", "heuristic", "rules_v1"}:
        return _classify_summary_intent_rule(text)
    if mode in {"rules_v2", "v2"}:
        return _classify_summary_intent_rules_v2(text)
    if mode in {"off", "none"}:
        return "statement"
    # Fail-safe fallback.
    return _classify_summary_intent_rule(text)


def _summary_topic_key(line: str) -> str:
    text = str(line or "").strip().lower()
    if not text:
        return ""
    if text.startswith("- "):
        text = text[2:]
    role = "unknown"
    if ":" in text:
        lhs, rhs = text.split(":", 1)
        role = lhs.strip() or role
        text = rhs.strip()
    intent = _classify_summary_intent(text)
    words = [w for w in re.findall(r"[a-z0-9_]+", text) if len(w) > 2]
    if not words:
        return f"{role}|{intent}|{text[:24]}"
    return f"{role}|{intent}|{' '.join(words[:4])}"


def _merge_rolling_summary(old_summary: str, new_summary: str) -> str:
    old_lines = [ln.strip() for ln in str(old_summary or "").splitlines() if ln.strip()]
    new_lines = [ln.strip() for ln in str(new_summary or "").splitlines() if ln.strip()]
    merged_lines: List[str] = []
    seen_keys: set[str] = set()

    def _accept(line: str) -> None:
        if line.lower() == "thread summary:":
            return
        key = _summary_topic_key(line)
        if not key:
            return
        if key in seen_keys:
            return
        seen_keys.add(key)
        merged_lines.append(line)

    for ln in old_lines:
        _accept(ln)
    for ln in new_lines:
        _accept(ln)

    if not merged_lines:
        return ""
    out = "Thread summary:\n" + "\n".join(f"- {ln[2:]}" if ln.startswith("- ") else f"- {ln}" for ln in merged_lines)
    if len(out) > _THREAD_SUMMARY_MAX_CHARS:
        out = "Thread summary:\n" + out[-(_THREAD_SUMMARY_MAX_CHARS - 16) :]
    return out


def _maybe_roll_thread_summary(node: Dict[str, Any]) -> Dict[str, Any]:
    messages = list(node.get("messages") or [])
    cap = max(4, min(200, _env_int(_THREAD_HISTORY_LIMIT_ENV, 32)))
    trigger = max(12, _env_int("QUENTIN_THREAD_SUMMARY_TRIGGER", _THREAD_SUMMARY_TRIGGER))
    trigger = min(trigger, max(8, cap - 4))
    keep_recent = max(4, _env_int("QUENTIN_THREAD_KEEP_RECENT", _THREAD_KEEP_RECENT))
    keep_recent = min(keep_recent, max(4, cap // 2))
    if len(messages) <= trigger:
        return node
    recent = messages[-keep_recent:]
    old = messages[: max(0, len(messages) - keep_recent)]
    old_summary = str(node.get("rolling_summary") or "").strip()
    new_summary = _summarize_thread_messages(old)
    merged = _merge_rolling_summary(old_summary, new_summary)
    if len(merged) > _THREAD_SUMMARY_MAX_CHARS:
        merged = merged[-_THREAD_SUMMARY_MAX_CHARS:]
    node["rolling_summary"] = merged
    node["summary_updated_at"] = _now_ts()
    node["messages"] = recent
    return node


def _thread_append(root: Path, platform: str, *, thread_id: str, role: str, text: str, user_id: str = "", meta: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    data = _thread_store_load(root, platform)
    threads = data["threads"]
    node = threads.get(thread_id)
    if not isinstance(node, dict):
        node = {"thread_id": thread_id, "created_at": _now_ts(), "updated_at": _now_ts(), "messages": []}
    messages = node.get("messages")
    if not isinstance(messages, list):
        messages = []
    item = {
        "id": f"msg_{uuid.uuid4().hex[:10]}",
        "ts": _now_ts(),
        "role": str(role or "agent"),
        "user_id": str(user_id or ""),
        "text": str(text or ""),
        "meta": dict(meta or {}),
    }
    messages.append(item)
    if len(messages) > 500:
        messages = messages[-250:]
    node["messages"] = messages
    node = _maybe_roll_thread_summary(node)
    cap = max(4, min(200, _env_int(_THREAD_HISTORY_LIMIT_ENV, 32)))
    mm = list(node.get("messages") or [])
    if len(mm) > cap:
        node["messages"] = mm[-cap:]
    node["updated_at"] = _now_ts()
    threads[thread_id] = node
    _thread_store_save(root, platform, data)
    return item


def _message_external_id(message_id: str, meta: Dict[str, Any]) -> str:
    md = dict(meta or {})
    return str(md.get("external_message_id") or md.get("message_id") or message_id or "").strip()


def _thread_find_message_index(messages: List[Dict[str, Any]], external_id: str) -> int:
    target = str(external_id or "").strip()
    if not target:
        return -1
    for i in range(len(messages) - 1, -1, -1):
        m = messages[i]
        if not isinstance(m, dict):
            continue
        mid = str((m.get("meta") or {}).get("external_message_id") or "")
        if mid and mid == target:
            return i
    return -1


def _thread_apply_event(
    root: Path,
    platform: str,
    *,
    thread_id: str,
    event_kind: str,
    text: str,
    user_id: str,
    message_id: str,
    meta: Dict[str, Any],
) -> Dict[str, Any]:
    data = _thread_store_load(root, platform)
    threads = data["threads"]
    node = threads.get(thread_id)
    if not isinstance(node, dict):
        node = {"thread_id": thread_id, "created_at": _now_ts(), "updated_at": _now_ts(), "messages": []}
    messages = list(node.get("messages") or [])
    ext_id = _message_external_id(message_id, meta)
    ek = str(event_kind or "message").strip().lower()
    if ek in {"edit", "message_edit", "edited"}:
        idx = _thread_find_message_index(messages, ext_id)
        if idx >= 0:
            item = dict(messages[idx])
            item["text"] = str(text or item.get("text") or "")
            item["ts"] = _now_ts()
            imeta = dict(item.get("meta") or {})
            imeta["edited"] = True
            imeta["edited_at"] = _now_ts()
            if ext_id:
                imeta["external_message_id"] = ext_id
            item["meta"] = imeta
            messages[idx] = item
            node["messages"] = messages
            node["updated_at"] = _now_ts()
            threads[thread_id] = node
            _thread_store_save(root, platform, data)
            return {"status": "ok", "event": "edit", "applied": True, "thread_id": thread_id}
        # no target: append as best-effort event
        _thread_append(
            root,
            platform,
            thread_id=thread_id,
            role="user",
            text=str(text or ""),
            user_id=user_id,
            meta={**dict(meta or {}), "external_message_id": ext_id, "edit_miss": True},
        )
        return {"status": "ok", "event": "edit", "applied": False, "thread_id": thread_id}
    if ek in {"delete", "message_delete", "deleted"}:
        idx = _thread_find_message_index(messages, ext_id)
        if idx >= 0:
            item = dict(messages[idx])
            item["text"] = "[deleted]"
            item["ts"] = _now_ts()
            imeta = dict(item.get("meta") or {})
            imeta["deleted"] = True
            imeta["deleted_at"] = _now_ts()
            if ext_id:
                imeta["external_message_id"] = ext_id
            item["meta"] = imeta
            messages[idx] = item
            node["messages"] = messages
            node["updated_at"] = _now_ts()
            threads[thread_id] = node
            _thread_store_save(root, platform, data)
            return {"status": "ok", "event": "delete", "applied": True, "thread_id": thread_id}
        return {"status": "ok", "event": "delete", "applied": False, "thread_id": thread_id}
    if ek in {"thread_move", "move_thread"}:
        old_thread = str(meta.get("old_thread_id") or "").strip()
        if old_thread and old_thread != thread_id:
            _thread_append(
                root,
                platform,
                thread_id=old_thread,
                role="system",
                text=f"message moved to {thread_id}",
                user_id="system",
                meta={"event_kind": "thread_move", "external_message_id": ext_id},
            )
        _thread_append(
            root,
            platform,
            thread_id=thread_id,
            role="system",
            text=f"message moved from {old_thread or 'unknown'}",
            user_id="system",
            meta={"event_kind": "thread_move", "external_message_id": ext_id},
        )
        return {"status": "ok", "event": "thread_move", "applied": True, "thread_id": thread_id}
    _thread_append(
        root,
        platform,
        thread_id=thread_id,
        role="user",
        text=str(text or ""),
        user_id=user_id,
        meta={**dict(meta or {}), "external_message_id": ext_id},
    )
    return {"status": "ok", "event": "message", "applied": True, "thread_id": thread_id}


def _thread_action(platform: str, req: Dict[str, Any], ctx: Any = None) -> Optional[Dict[str, Any]]:
    action = str(req.get("action") or "send").strip().lower()
    if action not in {"ingest", "fetch_thread", "list_threads"}:
        return None
    root = _repo_root_from_ctx(ctx)
    if action == "ingest":
        thread_id = _normalize_thread_id(req)
        text = str(req.get("text") or req.get("message") or "").strip()
        if not text:
            return {"status": "error", "error": "text/message is required for ingest"}
        item = _thread_append(
            root,
            platform,
            thread_id=thread_id,
            role="user",
            text=text,
            user_id=str(req.get("user_id") or ""),
            meta=dict(req.get("meta") or {}),
        )
        return {"status": "ok", "platform": platform, "thread_id": thread_id, "ingested": item}
    if action == "fetch_thread":
        thread_id = _normalize_thread_id(req)
        limit = max(1, min(500, int(req.get("limit") or 50)))
        data = _thread_store_load(root, platform)
        node = (data.get("threads") or {}).get(thread_id) or {}
        msgs = list(node.get("messages") or [])[-limit:]
        return {
            "status": "ok",
            "platform": platform,
            "thread_id": thread_id,
            "messages": msgs,
            "count": len(msgs),
            "rolling_summary": str(node.get("rolling_summary") or ""),
            "summary_updated_at": node.get("summary_updated_at"),
        }
    # list_threads
    limit = max(1, min(200, int(req.get("limit") or 50)))
    data = _thread_store_load(root, platform)
    rows: List[Dict[str, Any]] = []
    for tid, node in (data.get("threads") or {}).items():
        if not isinstance(node, dict):
            continue
        msgs = list(node.get("messages") or [])
        rows.append(
            {
                "thread_id": tid,
                "updated_at": float(node.get("updated_at") or 0.0),
                "message_count": len(msgs),
                "last_message_preview": str((msgs[-1] or {}).get("text") or "")[:120] if msgs else "",
            }
        )
    rows = sorted(rows, key=lambda x: float(x.get("updated_at") or 0.0), reverse=True)[:limit]
    return {"status": "ok", "platform": platform, "threads": rows, "count": len(rows)}


def _listener_state_path(root: Path) -> Path:
    return root / "data" / "channels" / "listener_state.json"


def _listener_state_load(root: Path) -> Dict[str, Any]:
    raw = _load_json(_listener_state_path(root), {"seen": {}, "dead_letters": []})
    if not isinstance(raw, dict):
        raw = {"seen": {}, "dead_letters": []}
    if not isinstance(raw.get("seen"), dict):
        raw["seen"] = {}
    if not isinstance(raw.get("dead_letters"), list):
        raw["dead_letters"] = []
    return raw


def _listener_state_save(root: Path, state: Dict[str, Any]) -> None:
    path = _listener_state_path(root)
    try:
        from quentin.runtime.session_write_lock import acquire_session_write_lock

        hold = acquire_session_write_lock(session_file=path, timeout_ms=2000, stale_ms=30_000)
        try:
            _save_json(path, state)
        finally:
            hold["release"]()
    except Exception:
        _save_json(path, state)


def _listener_event_id(*, platform: str, msg: Any, metadata: Dict[str, Any]) -> str:
    mid = str(getattr(msg, "message_id", "") or "").strip()
    kind = str((metadata or {}).get("event_kind") or (metadata or {}).get("event_type") or (metadata or {}).get("message_action") or "message").strip().lower()
    if mid:
        return f"{platform}:{mid}:{kind or 'message'}"
    base = {
        "platform": platform,
        "event_kind": kind or "message",
        "sender_id": str(getattr(msg, "sender_id", "") or ""),
        "text": str(getattr(msg, "text", "") or "")[:512],
        "metadata": metadata,
    }
    return f"{platform}:{_short_hash(_stable_json(base))}"


def _listener_seen_is_dup(state: Dict[str, Any], *, event_id: str, now: float) -> bool:
    seen = state.get("seen") or {}
    if not isinstance(seen, dict):
        return False
    # purge old ids
    purge_before = now - float(_LISTENER_DEDUPE_TTL_SEC)
    for k in list(seen.keys()):
        try:
            if float(seen.get(k) or 0.0) < purge_before:
                seen.pop(k, None)
        except Exception:
            seen.pop(k, None)
    ts = seen.get(event_id)
    if ts is not None:
        return True
    seen[event_id] = now
    state["seen"] = seen
    return False


def _listener_dead_letter(state: Dict[str, Any], *, event_id: str, platform: str, err: str, payload: Dict[str, Any]) -> None:
    dead = list(state.get("dead_letters") or [])
    dead.append(
        {
            "ts": _now_ts(),
            "event_id": event_id,
            "platform": platform,
            "error": str(err or "")[:400],
            "payload": payload,
        }
    )
    if len(dead) > 2000:
        dead = dead[-1000:]
    state["dead_letters"] = dead


async def _channels_listener_tool_async(req: Dict[str, Any], ctx: Any = None) -> Dict[str, Any]:
    action = str(req.get("action") or "status").strip().lower()
    platform = str(req.get("platform") or "").strip().lower()
    root = _repo_root_from_ctx(ctx)
    from quentin.infra.channels.listener_manager import listener_manager
    from quentin.infra.channels.base import InboundMessage

    auto_reply = bool(req.get("auto_reply", False))
    auto_reply_mode = str(req.get("auto_reply_mode") or "template").strip().lower()
    auto_reply_template = str(req.get("auto_reply_template") or "收到: {text}")
    auto_reply_send = bool(req.get("auto_reply_send", False))
    thread_history_limit = max(4, min(64, int(req.get("thread_history_limit") or _env_int(_THREAD_HISTORY_LIMIT_ENV, 32))))
    planner_history_limit = max(4, min(64, int(req.get("planner_history_limit") or _env_int(_THREAD_PLANNER_HISTORY_LIMIT_ENV, 12))))
    token_map = {
        "discord": str(req.get("discord_token") or os.getenv("DISCORD_BOT_TOKEN") or ""),
        "slack": str(req.get("slack_bot_token") or os.getenv("SLACK_BOT_TOKEN") or ""),
        "telegram": str(req.get("telegram_token") or os.getenv("TELEGRAM_BOT_TOKEN") or ""),
    }

    if action == "dead_letters":
        state = _listener_state_load(root)
        items = list(state.get("dead_letters") or [])
        if platform:
            items = [x for x in items if str(x.get("platform") or "") == platform]
        limit = max(1, min(500, int(req.get("limit") or 100)))
        items = sorted(items, key=lambda x: float(x.get("ts") or 0.0), reverse=True)[:limit]
        return {"status": "ok", "count": len(items), "dead_letters": items}

    if action == "clear_dead_letters":
        state = _listener_state_load(root)
        if platform:
            kept = [x for x in list(state.get("dead_letters") or []) if str(x.get("platform") or "") != platform]
            removed = len(list(state.get("dead_letters") or [])) - len(kept)
            state["dead_letters"] = kept
        else:
            removed = len(list(state.get("dead_letters") or []))
            state["dead_letters"] = []
        _listener_state_save(root, state)
        return {"status": "ok", "removed": int(removed)}

    if action == "redrive_dead_letters":
        state = _listener_state_load(root)
        all_dead = list(state.get("dead_letters") or [])
        if platform:
            candidates = [x for x in all_dead if str(x.get("platform") or "") == platform]
        else:
            candidates = list(all_dead)
        candidates = sorted(candidates, key=lambda x: float(x.get("ts") or 0.0))
        limit = max(1, min(200, int(req.get("limit") or 50)))
        candidates = candidates[:limit]
        replayed = 0
        succeeded = 0
        failed = 0
        redriven_ids = {str(x.get("event_id") or "") for x in candidates if str(x.get("event_id") or "")}
        kept = [x for x in all_dead if str(x.get("event_id") or "") not in redriven_ids]
        seen = state.get("seen") if isinstance(state.get("seen"), dict) else {}
        for x in candidates:
            eid = str(x.get("event_id") or "").strip()
            if eid and isinstance(seen, dict):
                seen.pop(eid, None)
        state["seen"] = seen
        state["dead_letters"] = kept
        _listener_state_save(root, state)

        for item in candidates:
            p = str(item.get("platform") or "").strip().lower()
            payload = item.get("payload") if isinstance(item.get("payload"), dict) else {}
            if not p or not isinstance(payload, dict):
                failed += 1
                continue
            md = dict(payload.get("metadata") or {})
            replayed += 1
            out = await _channels_listener_tool_async(
                {
                    "action": "inject",
                    "platform": p,
                    "text": str(payload.get("text") or ""),
                    "sender_id": str(payload.get("sender_id") or "user"),
                    "message_id": str(payload.get("message_id") or "") or str(uuid.uuid4()),
                    "metadata": md,
                    "auto_reply": bool(req.get("auto_reply", False)),
                    "auto_reply_mode": str(req.get("auto_reply_mode") or "template"),
                    "auto_reply_template": str(req.get("auto_reply_template") or "收到: {text}"),
                    "auto_reply_send": bool(req.get("auto_reply_send", False)),
                },
                ctx,
            )
            if isinstance(out, dict) and bool(out.get("dead_lettered")):
                failed += 1
            else:
                succeeded += 1
        return {
            "status": "ok",
            "action": "redrive_dead_letters",
            "requested": len(candidates),
            "replayed": replayed,
            "succeeded": succeeded,
            "failed": failed,
            "platform": platform or None,
        }

    async def _on_inbound(msg: InboundMessage) -> Dict[str, Any]:
        p = str(platform or msg.channel_id or "").strip().lower() or "unknown"
        md = dict(msg.metadata or {})
        thread_id = _thread_id_from_inbound(p, md)
        event_kind = str(md.get("event_kind") or md.get("event_type") or md.get("message_action") or "message").strip().lower()
        if not event_kind:
            event_kind = "message"
        if str(msg.message_id or "").strip() and "external_message_id" not in md:
            md["external_message_id"] = str(msg.message_id or "").strip()
        now = _now_ts()
        state = _listener_state_load(root)
        event_id = _listener_event_id(platform=p, msg=msg, metadata=md)
        if _listener_seen_is_dup(state, event_id=event_id, now=now):
            _listener_state_save(root, state)
            return {
                "event_id": event_id,
                "platform": p,
                "thread_id": thread_id,
                "event_kind": event_kind,
                "deduped": True,
            }
        _listener_state_save(root, state)

        last_err = ""
        for _attempt in range(_LISTENER_MAX_RETRIES + 1):
            try:
                _thread_apply_event(
                    root,
                    p,
                    thread_id=thread_id,
                    event_kind=event_kind,
                    text=str(msg.text or ""),
                    user_id=str(msg.sender_id or ""),
                    message_id=str(msg.message_id or ""),
                    meta=md,
                )
                _append_jsonl(
                    root / "data" / "channels" / f"inbound_{p}.jsonl",
                    {
                        "ts": _now_ts(),
                        "platform": p,
                        "event_id": event_id,
                        "thread_id": thread_id,
                        "event_kind": event_kind,
                        "text": str(msg.text or ""),
                        "sender_id": str(msg.sender_id or ""),
                        "message_id": str(msg.message_id or ""),
                        "metadata": md,
                    },
                )
                last_err = ""
                break
            except Exception as e:
                last_err = str(e)
        if last_err:
            state = _listener_state_load(root)
            _listener_dead_letter(
                state,
                event_id=event_id,
                platform=p,
                err=last_err,
                payload={
                    "thread_id": thread_id,
                    "text": str(msg.text or ""),
                    "sender_id": str(msg.sender_id or ""),
                    "message_id": str(msg.message_id or ""),
                    "metadata": md,
                },
            )
            _listener_state_save(root, state)
            return {
                "event_id": event_id,
                "platform": p,
                "thread_id": thread_id,
                "event_kind": event_kind,
                "dead_lettered": True,
                "error": last_err,
            }
        if auto_reply:
            if auto_reply_mode == "planner":
                thread_data = _thread_store_load(root, p)
                thread_node = (thread_data.get("threads") or {}).get(thread_id) or {}
                thread_history = list(thread_node.get("messages") or [])[-planner_history_limit:]
                thread_summary = str(thread_node.get("rolling_summary") or "")
                gen = _generate_planner_reply(
                    text=str(msg.text or ""),
                    platform=p,
                    thread_id=thread_id,
                    thread_history=thread_history,
                    thread_summary=thread_summary,
                    ctx=ctx,
                    fallback_template=auto_reply_template,
                )
                reply = str(gen.get("reply") or "")
                reply_mode = str(gen.get("mode") or "planner")
            else:
                reply = auto_reply_template.replace("{text}", str(msg.text or "")[:1000]).replace("{sender_id}", str(msg.sender_id or ""))
                reply_mode = "template"
            _thread_append(
                root,
                p,
                thread_id=thread_id,
                role="agent",
                text=reply,
                user_id="agent",
                meta={"auto_reply": True, "auto_reply_mode": reply_mode},
            )
            # keep thread history bounded by policy
            tdata = _thread_store_load(root, p)
            tnode = ((tdata.get("threads") or {}).get(thread_id) or {})
            if isinstance(tnode, dict):
                msgs = list(tnode.get("messages") or [])
                if len(msgs) > thread_history_limit:
                    tnode["messages"] = msgs[-thread_history_limit:]
                    (tdata.get("threads") or {})[thread_id] = tnode
                    _thread_store_save(root, p, tdata)
            _append_jsonl(
                root / "data" / "channels" / f"outbound_{p}.jsonl",
                {
                    "ts": _now_ts(),
                    "platform": p,
                    "thread_id": thread_id,
                    "text": reply,
                    "auto_reply": True,
                    "auto_reply_mode": reply_mode,
                },
            )
            if auto_reply_send and p in {"discord", "slack", "telegram"}:
                target_id = str(md.get("channel_id") or md.get("chat_id") or "").strip()
                token = token_map.get(p) or ""
                if target_id and token:
                    await _send_via_adapter(p, token=token, target_id=target_id, text=reply)
            return {
                "event_id": event_id,
                "platform": p,
                "thread_id": thread_id,
                "event_kind": event_kind,
                "deduped": False,
                "auto_reply": True,
                "auto_reply_mode": reply_mode,
            }
        return {
            "event_id": event_id,
            "platform": p,
            "thread_id": thread_id,
            "event_kind": event_kind,
            "deduped": False,
            "auto_reply": False,
        }

    if action in {"inject", "simulate_inbound"}:
        # Offline-friendly: directly feed an inbound event into the same pipeline used by live listeners.
        if not platform:
            platform = str(req.get("channel_id") or req.get("channel") or "").strip().lower()
        if not platform:
            return {"status": "error", "error": "platform required"}
        md = dict(req.get("metadata") or req.get("meta") or {})
        ek = str(req.get("event_kind") or md.get("event_kind") or "").strip().lower()
        if ek and "event_kind" not in md:
            md["event_kind"] = ek
        msg = InboundMessage(
            text=str(req.get("text") or ""),
            sender_id=str(req.get("sender_id") or req.get("user_id") or "user"),
            channel_id=platform,
            message_id=str(req.get("message_id") or "").strip() or str(uuid.uuid4()),
            metadata=md,
        )
        out = await _on_inbound(msg)
        if not isinstance(out, dict):
            out = {}
        out.update({"status": "ok", "action": "inject", "platform": platform})
        return out

    if action == "start":
        if not platform:
            return {"status": "error", "error": "platform required"}
        if platform == "slack":
            cfg = {
                "app_token": str(req.get("app_token") or os.getenv("SLACK_APP_TOKEN") or ""),
                "bot_token": str(req.get("bot_token") or os.getenv("SLACK_BOT_TOKEN") or ""),
            }
        elif platform == "discord":
            cfg = {"token": str(req.get("token") or os.getenv("DISCORD_BOT_TOKEN") or "")}
        elif platform == "telegram":
            cfg = {"token": str(req.get("token") or os.getenv("TELEGRAM_BOT_TOKEN") or "")}
        else:
            return {"status": "error", "error": f"unsupported platform: {platform}"}
        out = listener_manager.start(platform, config=cfg, on_message=_on_inbound)
        out["platform"] = platform
        return out
    if action == "stop":
        if not platform:
            return {"status": "error", "error": "platform required"}
        return listener_manager.stop(platform)
    if action == "poll":
        if not platform:
            return {"status": "error", "error": "platform required"}
        return listener_manager.poll(platform, from_seq=int(req.get("from_seq") or 0), limit=int(req.get("limit") or 100))
    # status default
    if platform:
        return listener_manager.status(platform)
    return listener_manager.status()


def channels_listener_tool(req: Dict[str, Any], ctx: Any = None) -> Dict[str, Any]:
    """
    Sync wrapper for direct callers/tests.

    ToolManager can call the async variant `channels_listener_tool_async` to avoid
    `asyncio.run()` inside an active event loop.
    """
    import asyncio

    action = str((req or {}).get("action") or "status").strip().lower()
    platform = str((req or {}).get("platform") or "").strip().lower()

    # IMPORTANT: `listener_manager.start()` is sync and may itself call `asyncio.run(on_message(...))`
    # in tests/stubs. If we wrapped "start" inside `asyncio.run(_channels_listener_tool_async(...))`,
    # we'd create nested event loops. So we keep "start/stop/poll/status" as pure sync paths here.
    if action in {"start", "stop", "poll", "status"}:
        from quentin.infra.channels.listener_manager import listener_manager

        if action == "start":
            if not platform:
                return {"status": "error", "error": "platform required"}
            if platform == "slack":
                cfg = {
                    "app_token": str(req.get("app_token") or os.getenv("SLACK_APP_TOKEN") or ""),
                    "bot_token": str(req.get("bot_token") or os.getenv("SLACK_BOT_TOKEN") or ""),
                }
            elif platform == "discord":
                cfg = {"token": str(req.get("token") or os.getenv("DISCORD_BOT_TOKEN") or "")}
            elif platform == "telegram":
                cfg = {"token": str(req.get("token") or os.getenv("TELEGRAM_BOT_TOKEN") or "")}
            else:
                return {"status": "error", "error": f"unsupported platform: {platform}"}

            auto_reply = bool(req.get("auto_reply", False))
            auto_reply_mode = str(req.get("auto_reply_mode") or "template").strip().lower()
            auto_reply_template = str(req.get("auto_reply_template") or "收到: {text}")
            auto_reply_send = bool(req.get("auto_reply_send", False))
            thread_history_limit = int(req.get("thread_history_limit") or 32)
            planner_history_limit = int(req.get("planner_history_limit") or 12)

            async def _on_message(msg):  # listener_manager stubs expect a coroutine.
                md = dict(getattr(msg, "metadata", {}) or {})
                return await _channels_listener_tool_async(
                    {
                        "action": "inject",
                        "platform": platform,
                        "text": str(getattr(msg, "text", "") or ""),
                        "sender_id": str(getattr(msg, "sender_id", "") or ""),
                        "message_id": str(getattr(msg, "message_id", "") or ""),
                        "metadata": md,
                        "auto_reply": auto_reply,
                        "auto_reply_mode": auto_reply_mode,
                        "auto_reply_template": auto_reply_template,
                        "auto_reply_send": auto_reply_send,
                        "thread_history_limit": thread_history_limit,
                        "planner_history_limit": planner_history_limit,
                    },
                    ctx,
                )

            out = listener_manager.start(platform, config=cfg, on_message=_on_message)
            if not isinstance(out, dict):
                out = {"status": "ok"}
            out["platform"] = platform
            return out

        if action == "stop":
            if not platform:
                return {"status": "error", "error": "platform required"}
            return listener_manager.stop(platform)

        if action == "poll":
            if not platform:
                return {"status": "error", "error": "platform required"}
            return listener_manager.poll(platform, from_seq=int(req.get("from_seq") or 0), limit=int(req.get("limit") or 100))

        # status default
        if platform:
            return listener_manager.status(platform)
        return listener_manager.status()

    # Remaining actions require the async implementation (inject, dead_letters, clear_dead_letters, etc.).
    try:
        loop = asyncio.get_running_loop()
        if loop.is_running():
            return {"status": "error", "error": "channels.listener must be awaited (use channels_listener_tool_async)"}
    except RuntimeError:
        pass
    return asyncio.run(_channels_listener_tool_async(req, ctx))


async def channels_listener_tool_async(req: Dict[str, Any], ctx: Any = None) -> Dict[str, Any]:
    return await _channels_listener_tool_async(req, ctx)


def web_readability_tool(req: Dict[str, Any], ctx: Any = None) -> Dict[str, Any]:
    url = str(req.get("url") or "").strip()
    html = str(req.get("html") or "")
    max_chars = int(req.get("max_chars") or 12000)
    apply_site_patch = bool(req.get("apply_site_patch", True))
    if not html and url:
        with urllib.request.urlopen(url, timeout=20) as resp:
            html = resp.read().decode("utf-8", errors="ignore")
    if not html:
        return {"status": "error", "error": "url or html is required"}
    site_patch = {"site": "generic", "removed_blocks": 0, "rules": []}
    patched = html
    if apply_site_patch:
        site, patched, site_patch = _apply_site_patch(url, html)
        site_patch["site"] = site
    clean = _strip_html_noise(patched)
    diff_metrics = _readability_diff_metrics(original_html=html, patched_html=patched, clean_text=clean)
    return {
        "status": "ok",
        "url": url,
        "content": clean[:max_chars],
        "content_length": len(clean),
        "site_patch": site_patch,
        "diff_metrics": diff_metrics,
    }


def _web_normalize_whitespace(value: str) -> str:
    return (
        str(value or "")
        .replace("\r", "")
        .strip()
        .replace("\t", " ")
    )


def _web_strip_tags(value: str) -> str:
    # Minimal HTML tag stripper. Used as fallback when readability isn't available.
    return re.sub(r"<[^>]+>", "", str(value or ""))


def _web_html_to_markdown(html: str) -> Dict[str, str]:
    """
    Ported from OpenClaw's web-fetch-utils.ts (htmlToMarkdown/markdownToText).
    This is intentionally lightweight and dependency-free.
    """
    raw = str(html or "")
    title = ""
    m = re.search(r"<title[^>]*>([\s\S]*?)</title>", raw, flags=re.IGNORECASE)
    if m:
        title = _web_normalize_whitespace(_web_strip_tags(m.group(1)))

    text = raw
    text = re.sub(r"<script[\s\S]*?</script>", "", text, flags=re.IGNORECASE)
    text = re.sub(r"<style[\s\S]*?</style>", "", text, flags=re.IGNORECASE)
    text = re.sub(r"<noscript[\s\S]*?</noscript>", "", text, flags=re.IGNORECASE)

    def _a_sub(match: re.Match[str]) -> str:
        href = str(match.group(1) or "")
        body = str(match.group(2) or "")
        label = _web_normalize_whitespace(_web_strip_tags(body))
        if not label:
            return href
        return f"[{label}]({href})"

    text = re.sub(r"<a\s+[^>]*href=[\"']([^\"']+)[\"'][^>]*>([\s\S]*?)</a>", _a_sub, text, flags=re.IGNORECASE)

    def _h_sub(match: re.Match[str]) -> str:
        level = int(match.group(1) or "1")
        level = max(1, min(6, level))
        body = str(match.group(2) or "")
        label = _web_normalize_whitespace(_web_strip_tags(body))
        return f"\n{'#' * level} {label}\n"

    text = re.sub(r"<h([1-6])[^>]*>([\s\S]*?)</h\\1>", _h_sub, text, flags=re.IGNORECASE)

    def _li_sub(match: re.Match[str]) -> str:
        body = str(match.group(1) or "")
        label = _web_normalize_whitespace(_web_strip_tags(body))
        return f"\n- {label}" if label else ""

    text = re.sub(r"<li[^>]*>([\s\S]*?)</li>", _li_sub, text, flags=re.IGNORECASE)

    text = re.sub(r"<(br|hr)\\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"</(p|div|section|article|header|footer|table|tr|ul|ol)>", "\n", text, flags=re.IGNORECASE)
    text = _web_strip_tags(text)
    text = _web_normalize_whitespace(text)
    # Normalize repeated blank lines/spaces.
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    text = text.strip()
    return {"text": text, "title": title}


def _web_markdown_to_text(markdown: str) -> str:
    text = str(markdown or "")
    text = re.sub(r"!\[[^\]]*]\([^)]+\)", "", text)
    text = re.sub(r"\[([^\]]+)]\([^)]+\)", r"\\1", text)
    text = re.sub(r"```[\s\S]*?```", lambda m: re.sub(r"```[^\n]*\n?", "", m.group(0)).replace("```", ""), text)
    text = re.sub(r"`([^`]+)`", r"\\1", text)
    text = re.sub(r"^#{1,6}\\s+", "", text, flags=re.MULTILINE)
    text = re.sub(r"^\\s*[-*+]\\s+", "", text, flags=re.MULTILINE)
    text = re.sub(r"^\\s*\\d+\\.\\s+", "", text, flags=re.MULTILINE)
    text = _web_normalize_whitespace(text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return text


def _web_truncate_text(value: str, max_chars: int) -> Tuple[str, bool]:
    s = str(value or "")
    if max_chars <= 0:
        return ("", True)
    if len(s) <= max_chars:
        return (s, False)
    return (s[: max(0, int(max_chars))], True)


def _web_looks_like_html(value: str) -> bool:
    head = str(value or "").lstrip().lower()[:256]
    return head.startswith("<!doctype html") or head.startswith("<html") or "<body" in head


def _web_is_private_host(host: str) -> bool:
    h = str(host or "").strip().lower()
    if not h:
        return True
    if h in {"localhost", "127.0.0.1", "::1"}:
        return True
    if h.endswith(".local"):
        return True
    # IP literal checks (covers IPv4 and IPv6).
    try:
        ip = ip_address(h)
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_reserved or ip.is_unspecified:
            return True
    except Exception:
        pass
    # Common RFC1918 patterns in hostname form (best-effort).
    if re.fullmatch(r"127(?:\\.[0-9]{1,3}){3}", h):
        return True
    if re.fullmatch(r"10(?:\\.[0-9]{1,3}){3}", h):
        return True
    if re.fullmatch(r"192\\.168(?:\\.[0-9]{1,3}){2}", h):
        return True
    if re.fullmatch(r"172\\.(?:1[6-9]|2\\d|3[0-1])(?:\\.[0-9]{1,3}){2}", h):
        return True
    return False


class _LimitedRedirect(urllib.request.HTTPRedirectHandler):
    def __init__(self, max_redirects: int) -> None:
        super().__init__()
        self._max = max(0, int(max_redirects))
        self._count = 0

    def redirect_request(self, req, fp, code, msg, hdrs, newurl):  # type: ignore[override]
        self._count += 1
        if self._count > self._max:
            raise urllib.error.HTTPError(req.full_url, code, "too many redirects", hdrs, fp)  # type: ignore[attr-defined]
        return super().redirect_request(req, fp, code, msg, hdrs, newurl)


def web_fetch_tool(req: Dict[str, Any], ctx: Any = None) -> Dict[str, Any]:
    """
    OpenClaw-parity web fetch tool:
    - SSRF guard (blocks localhost/private IP ranges and non-http(s) schemes).
    - Optional cache.
    - Extract mode: markdown or text.
    - Offline-friendly: if `html` is provided, no network fetch is attempted.
    """
    _ = ctx
    url = str(req.get("url") or "").strip()
    html_override = str(req.get("html") or "")
    extract_mode = str(req.get("extract_mode") or req.get("extractMode") or "markdown").strip().lower()
    if extract_mode not in {"markdown", "text"}:
        extract_mode = "markdown"
    max_chars = int(req.get("max_chars") or req.get("maxChars") or 50_000)
    timeout_sec = float(req.get("timeout_seconds") or req.get("timeoutSeconds") or 20.0)
    max_redirects = int(req.get("max_redirects") or req.get("maxRedirects") or 3)
    cache_ttl_sec = int(req.get("cache_ttl_sec") or req.get("cacheTtlSec") or 600)
    cache_enabled = bool(req.get("cache_enabled", True))
    user_agent = str(req.get("user_agent") or req.get("userAgent") or "Mozilla/5.0 QuentinWebFetch/1.0").strip()
    include_warning = bool(req.get("include_warning", True))
    apply_site_patch = bool(req.get("apply_site_patch", True))

    if not url and not html_override:
        return {"status": "error", "error": "url or html is required"}

    if url:
        parsed = urlparse(url)
        scheme = str(parsed.scheme or "").lower()
        host = str(parsed.hostname or "").strip()
        if scheme not in {"http", "https"}:
            return {"status": "error", "error": f"blocked url scheme: {scheme or 'unknown'}"}
        if _web_is_private_host(host):
            return {"status": "error", "error": f"blocked private/loopback host: {host or 'unknown'}"}

    root = _repo_root_from_ctx(ctx)
    cache_path = root / "data" / "web_fetch_cache.json"

    def _read_cache(key: str) -> Optional[Dict[str, Any]]:
        if not cache_enabled or cache_ttl_sec <= 0:
            return None
        try:
            from quentin.runtime.session_write_lock import acquire_session_write_lock
            hold = acquire_session_write_lock(session_file=cache_path, timeout_ms=1200, stale_ms=30_000)
            try:
                db = _load_json(cache_path, {"entries": {}})
            finally:
                hold["release"]()
        except Exception:
            db = _load_json(cache_path, {"entries": {}})
        entries = (db or {}).get("entries") if isinstance(db, dict) else {}
        if not isinstance(entries, dict):
            return None
        rec = entries.get(key)
        if not isinstance(rec, dict):
            return None
        ts = float(rec.get("ts") or 0.0)
        if ts <= 0:
            return None
        if (_now_ts() - ts) > float(cache_ttl_sec):
            return None
        return rec

    def _write_cache(key: str, value: Dict[str, Any]) -> None:
        if not cache_enabled or cache_ttl_sec <= 0:
            return
        try:
            from quentin.runtime.session_write_lock import acquire_session_write_lock
            hold = acquire_session_write_lock(session_file=cache_path, timeout_ms=1200, stale_ms=30_000)
            try:
                db = _load_json(cache_path, {"entries": {}})
                if not isinstance(db, dict):
                    db = {"entries": {}}
                if not isinstance(db.get("entries"), dict):
                    db["entries"] = {}
                db["entries"][key] = value
                # Keep bounded.
                if len(db["entries"]) > 250:
                    # Drop oldest 50
                    rows = sorted(
                        [(k, v) for k, v in db["entries"].items() if isinstance(v, dict)],
                        key=lambda kv: float((kv[1] or {}).get("ts") or 0.0),
                    )
                    for k, _v in rows[:50]:
                        db["entries"].pop(k, None)
                _save_json(cache_path, db)
            finally:
                hold["release"]()
        except Exception:
            try:
                db = _load_json(cache_path, {"entries": {}})
                if not isinstance(db, dict):
                    db = {"entries": {}}
                if not isinstance(db.get("entries"), dict):
                    db["entries"] = {}
                db["entries"][key] = value
                _save_json(cache_path, db)
            except Exception:
                pass

    cache_key = hashlib.md5(f"{url}|{extract_mode}|{max_chars}|{apply_site_patch}".encode("utf-8")).hexdigest()
    if not html_override and url:
        cached = _read_cache(cache_key)
        if cached is not None:
            return {"status": "ok", "cached": True, **cached.get("payload", {})}

    status_code = 0
    content_type = ""
    raw_text = ""
    fetch_error = ""
    fetched_via = "override_html" if html_override else "http"

    if html_override:
        raw_text = html_override
        content_type = "text/html; charset=utf-8"
        status_code = 200
    else:
        try:
            opener = urllib.request.build_opener(_LimitedRedirect(max_redirects))
            req_obj = urllib.request.Request(url, headers={"User-Agent": user_agent})
            with opener.open(req_obj, timeout=max(1.0, float(timeout_sec))) as resp:
                status_code = int(getattr(resp, "status", 200) or 200)
                content_type = str(resp.headers.get("Content-Type") or "")
                raw_text = resp.read().decode("utf-8", errors="ignore")
        except Exception as e:
            fetch_error = str(e)
            raw_text = ""

    is_html = ("text/html" in str(content_type or "").lower()) or _web_looks_like_html(raw_text)
    site_patch = {"site": "generic", "removed_blocks": 0, "rules": []}
    patched_html = raw_text
    if is_html and apply_site_patch:
        site, patched_html, site_patch = _apply_site_patch(url, raw_text)
        site_patch["site"] = site

    title = ""
    extracted = ""
    if raw_text and is_html:
        if extract_mode == "text":
            extracted = _strip_html_noise(patched_html)
        else:
            rendered = _web_html_to_markdown(patched_html)
            title = rendered.get("title") or ""
            extracted = rendered.get("text") or ""
            if extract_mode == "text":
                extracted = _web_markdown_to_text(extracted)
    else:
        extracted = str(raw_text or "").strip()

    extracted, truncated = _web_truncate_text(extracted, max_chars)

    wrapped = ""
    try:
        from quentin.security.external_content import wrap_web_content, wrap_external_content
        if is_html:
            wrapped = wrap_web_content(extracted, source="web_fetch")
        else:
            wrapped = wrap_external_content(extracted, source="web_fetch", include_warning=include_warning)
    except Exception:
        wrapped = extracted

    out = {
        "status": "ok" if extracted or not fetch_error else "error",
        "url": url,
        "status_code": status_code,
        "content_type": content_type,
        "extract_mode": extract_mode,
        "title": title or None,
        "content": extracted,
        "wrapped_content": wrapped,
        "truncated": bool(truncated),
        "site_patch": site_patch if is_html else None,
        "fetched_via": fetched_via,
        "error": fetch_error or None,
    }
    if not html_override and url and cache_enabled and (out.get("status") == "ok"):
        _write_cache(
            cache_key,
            {
                "ts": _now_ts(),
                "payload": out,
            },
        )
    return out


def web_search_tool(req: Dict[str, Any], ctx: Any = None) -> Dict[str, Any]:
    """
    OpenClaw-style web search tool (offline-first).

    Supported inputs:
    - query (string)
    - max_results / maxResults (int)
    - corpus: optional local search corpus list[{title,url,snippet,text,content}]
    - mock_items: explicit provider-like items list[{title,url,snippet}]

    Behavior:
    - Empty query is safe and returns an empty result set.
    - If `mock_items` is provided, normalize and return them.
    - Else if `corpus` is provided, run a simple lexical ranking.
    - Else return empty results with `mode=empty_provider`.
    """
    _ = ctx
    query = str(req.get("query") or "").strip()
    max_results = max(1, min(20, int(req.get("max_results") or req.get("maxResults") or 5)))
    include_warning = bool(req.get("include_warning", True))

    if not query:
        return {"status": "ok", "query": query, "results": [], "count": 0, "mode": "empty_query"}

    def _wrap(txt: str) -> str:
        try:
            from quentin.security.external_content import wrap_external_content

            return wrap_external_content(txt, source="web_search", include_warning=include_warning)
        except Exception:
            return txt

    mock_items = req.get("mock_items")
    if isinstance(mock_items, list):
        rows: List[Dict[str, Any]] = []
        for it in mock_items:
            if not isinstance(it, dict):
                continue
            title = str(it.get("title") or "").strip()
            url = str(it.get("url") or it.get("link") or "").strip()
            snippet = str(it.get("snippet") or it.get("text") or it.get("content") or "").strip()
            rows.append({"title": title, "url": url, "snippet": snippet, "content": _wrap(snippet)})
        rows = rows[:max_results]
        return {"status": "ok", "query": query, "results": rows, "count": len(rows), "mode": "mock_items"}

    corpus = req.get("corpus")
    if isinstance(corpus, list):
        q_terms = [t for t in re.findall(r"[a-z0-9_]+", query.lower()) if t]
        scored: List[Tuple[float, Dict[str, Any]]] = []
        for item in corpus:
            if not isinstance(item, dict):
                continue
            title = str(item.get("title") or "").strip()
            url = str(item.get("url") or item.get("link") or "").strip()
            text = str(item.get("snippet") or item.get("text") or item.get("content") or "").strip()
            hay = f"{title}\n{text}".lower()
            score = 0.0
            for t in q_terms:
                if t in hay:
                    score += 1.0
            if score <= 0:
                continue
            # prefer title matches slightly.
            tscore = 0.0
            low_title = title.lower()
            for t in q_terms:
                if t in low_title:
                    tscore += 0.3
            score += tscore
            scored.append((score, {"title": title, "url": url, "snippet": text[:1200], "content": _wrap(text[:1200])}))
        scored.sort(key=lambda x: x[0], reverse=True)
        rows = [r for _s, r in scored[:max_results]]
        return {"status": "ok", "query": query, "results": rows, "count": len(rows), "mode": "local_corpus"}

    return {"status": "ok", "query": query, "results": [], "count": 0, "mode": "empty_provider"}


def image_tool(req: Dict[str, Any], ctx: Any = None) -> Dict[str, Any]:
    path = str(req.get("path") or "").strip()
    text_hint = str(req.get("text_hint") or "")
    if not path:
        return {"status": "error", "error": "path is required"}
    p = Path(path).expanduser().resolve()
    if not p.exists():
        return {"status": "error", "error": f"image not found: {p}"}
    raw = p.read_bytes()
    out: Dict[str, Any] = {
        "status": "ok",
        "path": str(p),
        "bytes": len(raw),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "ocr_text": "",
        "ocr_engine": "none",
        "features": {},
        "token_budget": {},
    }
    ocr_mode = str(req.get("ocr_mode") or "auto").strip().lower()
    ocr_min_conf = float(req.get("ocr_min_confidence") or 0.35)
    ocr_allow_fallback = bool(req.get("ocr_allow_fallback", True))
    crop = dict(req.get("crop") or {})
    grayscale = bool(req.get("grayscale", True))
    threshold = req.get("threshold")
    try:
        from PIL import Image  # type: ignore

        with Image.open(p) as im:
            if crop:
                x = max(0, int(crop.get("x") or 0))
                y = max(0, int(crop.get("y") or 0))
                w = max(1, int(crop.get("w") or im.width))
                h = max(1, int(crop.get("h") or im.height))
                im = im.crop((x, y, min(im.width, x + w), min(im.height, y + h)))
            mp = (int(im.width) * int(im.height)) / 1_000_000.0
            vision_tokens = int(max(256, min(8192, mp * 900)))
            suggested_max_dim = 1024 if mp > 2.0 else 1536
            out["features"] = {
                "format": str(im.format or ""),
                "mode": str(im.mode or ""),
                "width": int(im.width),
                "height": int(im.height),
                "cropped": bool(crop),
            }
            out["token_budget"] = {
                "estimated_vision_tokens": vision_tokens,
                "recommended_max_dimension": suggested_max_dim,
                "recommended_strategy": (
                    "crop_then_ocr"
                    if mp > 3.0
                    else ("direct_ocr" if mp <= 1.5 else "resize_then_ocr")
                ),
            }
    except Exception:
        pass
    def _estimate_confidence(text: str) -> float:
        s = str(text or "").strip()
        if not s:
            return 0.0
        n = len(s)
        alnum = sum(1 for ch in s if ch.isalnum())
        printable = sum(1 for ch in s if (31 < ord(ch) < 127) or ch in "\n\r\t ")
        odd = sum(1 for ch in s if ch in {"�", "□", "�"})
        base = min(1.0, n / 120.0)
        score = (0.45 * base) + (0.35 * (alnum / max(1, n))) + (0.2 * (printable / max(1, n))) - (0.35 * (odd / max(1, n)))
        return max(0.0, min(1.0, score))

    def _run_vision_api() -> Tuple[str, str, Dict[str, Any]]:
        endpoint = str(req.get("vision_endpoint") or os.getenv("QUENTIN_OCR_VISION_ENDPOINT") or "").strip()
        if not endpoint:
            return text_hint[:8000], "vision_api_unconfigured", {}
        try:
            res = _http_post_json(
                endpoint,
                {
                    "path": str(p),
                    "sha256": out.get("sha256"),
                    "text_hint": text_hint,
                    "meta": dict(req.get("meta") or {}),
                },
                timeout=float(req.get("vision_timeout_sec") or 20.0),
            )
            body = str(res.get("body") or "")
            txt = ""
            conf = None
            try:
                bj = json.loads(body) if body else {}
                txt = str(bj.get("ocr_text") or bj.get("text") or "")
                raw_conf = bj.get("confidence")
                if raw_conf is not None:
                    conf = float(raw_conf)
            except Exception:
                txt = body
            if text_hint and txt:
                txt = f"{text_hint}\n{txt}"
            extra: Dict[str, Any] = {"vision_response": {"status_code": int(res.get("status_code") or 0)}}
            if conf is not None:
                extra["ocr_confidence"] = max(0.0, min(1.0, conf))
            return (txt[:8000] if txt else text_hint[:8000]), "vision_api", extra
        except Exception:
            return text_hint[:8000], "vision_api_error", {}

    def _run_tesseract_or_hint(*, mode: str) -> Tuple[str, str]:
        try:
            import pytesseract  # type: ignore
            from PIL import Image  # type: ignore

            if mode in {"hint", "manual"}:
                raise RuntimeError("hint mode")
            img = Image.open(p)
            if crop:
                x = max(0, int(crop.get("x") or 0))
                y = max(0, int(crop.get("y") or 0))
                w = max(1, int(crop.get("w") or img.width))
                h = max(1, int(crop.get("h") or img.height))
                img = img.crop((x, y, min(img.width, x + w), min(img.height, y + h)))
            if grayscale:
                img = img.convert("L")
            if threshold is not None:
                t = max(0, min(255, int(threshold)))
                img = img.point(lambda px: 255 if int(px) >= t else 0)
            txt = pytesseract.image_to_string(img)
            if text_hint:
                txt = f"{text_hint}\n{txt}"
            return txt[:8000], "tesseract"
        except Exception:
            # Fallback: call `tesseract` CLI directly when pytesseract isn't available.
            # This keeps OCR capability usable in minimal environments.
            try:
                if mode in {"hint", "manual"}:
                    raise RuntimeError("hint mode")
                import shutil
                import subprocess
                import tempfile
                from PIL import Image  # type: ignore

                if not shutil.which("tesseract"):
                    raise RuntimeError("tesseract binary not found")

                img = Image.open(p)
                if crop:
                    x = max(0, int(crop.get("x") or 0))
                    y = max(0, int(crop.get("y") or 0))
                    w = max(1, int(crop.get("w") or img.width))
                    h = max(1, int(crop.get("h") or img.height))
                    img = img.crop((x, y, min(img.width, x + w), min(img.height, y + h)))
                if grayscale:
                    img = img.convert("L")
                if threshold is not None:
                    t = max(0, min(255, int(threshold)))
                    img = img.point(lambda px: 255 if int(px) >= t else 0)

                tmp_path = None
                try:
                    with tempfile.NamedTemporaryFile(prefix="tesseract_", suffix=".png", delete=False) as tf:
                        tmp_path = tf.name
                    img.save(tmp_path)
                    # `tesseract <img> stdout` prints OCR text to stdout.
                    proc = subprocess.run(
                        ["tesseract", tmp_path, "stdout"],
                        capture_output=True,
                        text=True,
                        timeout=float(req.get("tesseract_timeout_sec") or 20.0),
                    )
                    txt = (proc.stdout or "").strip()
                    if text_hint and txt:
                        txt = f"{text_hint}\n{txt}"
                    return (txt[:8000] if txt else text_hint[:8000]), "tesseract_cli"
                finally:
                    if tmp_path:
                        try:
                            os.unlink(tmp_path)
                        except Exception:
                            pass
            except Exception:
                return text_hint[:8000], ("hint" if mode in {"auto", "tesseract", "hint", "manual"} else str(mode or "hint"))

    if ocr_mode in {"none", "off"}:
        out["ocr_text"] = text_hint[:8000]
        out["ocr_engine"] = "none"
    elif ocr_mode in {"vision", "vision_api"}:
        txt, eng, extra = _run_vision_api()
        out["ocr_text"] = txt
        out["ocr_engine"] = eng
        out.update(extra)
    else:
        txt, eng = _run_tesseract_or_hint(mode=ocr_mode)
        out["ocr_text"] = txt
        out["ocr_engine"] = eng

    conf = out.get("ocr_confidence")
    if conf is None:
        conf = _estimate_confidence(str(out.get("ocr_text") or ""))
    conf_v = max(0.0, min(1.0, float(conf)))
    out["ocr_confidence"] = conf_v
    out["ocr_primary_engine"] = str(out.get("ocr_engine") or "")
    out["ocr_fallback_used"] = False

    if ocr_allow_fallback and ocr_mode in {"auto", "tesseract", "hint", "manual"} and conf_v < ocr_min_conf:
        vtxt, veng, vextra = _run_vision_api()
        vconf = float(vextra.get("ocr_confidence") or _estimate_confidence(vtxt))
        if vconf > conf_v and str(veng).startswith("vision_api"):
            out["ocr_text"] = vtxt
            out["ocr_engine"] = veng
            out["ocr_confidence"] = max(0.0, min(1.0, vconf))
            out["ocr_fallback_used"] = True
            out.update(vextra)
    if bool(req.get("save_ocr_memory", False)):
        root = _repo_root_from_ctx(ctx)
        mem = root / "data" / "image_ocr_memory.jsonl"
        _append_jsonl(
            mem,
            {
                "ts": _now_ts(),
                "path": str(p),
                "sha256": out.get("sha256"),
                "ocr_engine": out.get("ocr_engine"),
                "ocr_text": str(out.get("ocr_text") or "")[:4000],
                "meta": dict(req.get("meta") or {}),
            },
        )
        out["memory_saved"] = True
        out["memory_path"] = str(mem)
    return out


def canvas_tool(req: Dict[str, Any], ctx: Any = None) -> Dict[str, Any]:
    action = str(req.get("action") or "create").strip().lower()
    root = _repo_root_from_ctx(ctx)
    path = root / "data" / "canvas_components.json"
    ack_path = root / "data" / "canvas_component_acks.jsonl"
    state = _load_json(path, {"components": {}})
    if not isinstance(state, dict):
        state = {"components": {}}
    comps = state.get("components")
    if not isinstance(comps, dict):
        comps = {}

    if action == "list":
        include_deleted = bool(req.get("include_deleted", False))
        rows = [v for v in comps.values() if isinstance(v, dict)]
        if not include_deleted:
            rows = [v for v in rows if str(v.get("status") or "active") != "deleted"]
        rows = sorted(rows, key=lambda x: float(x.get("updated_at") or 0.0), reverse=True)
        return {"status": "ok", "count": len(rows), "components": rows[: int(req.get("limit") or 200)]}

    if action == "get":
        cid = str(req.get("component_id") or "").strip()
        node = comps.get(cid)
        if not cid or not isinstance(node, dict):
            return {"status": "error", "error": "component not found"}
        return {"status": "ok", "component": node}

    if action == "ack":
        cid = str(req.get("component_id") or "").strip()
        node = comps.get(cid)
        if not cid or not isinstance(node, dict):
            return {"status": "error", "error": "component not found"}
        ack = {
            "ts": _now_ts(),
            "component_id": cid,
            "ack_type": str(req.get("ack_type") or "received"),
            "actor": str(req.get("actor") or "ui"),
            "meta": dict(req.get("meta") or {}),
        }
        _append_jsonl(ack_path, ack)
        node["last_ack"] = ack
        node["updated_at"] = _now_ts()
        comps[cid] = node
        state["components"] = comps
        _save_json(path, state)
        return {"status": "ok", "acked": True, "ack": ack}

    if action == "list_acks":
        cid = str(req.get("component_id") or "").strip()
        limit = max(1, min(500, int(req.get("limit") or 100)))
        rows: List[Dict[str, Any]] = []
        if ack_path.exists():
            for line in ack_path.read_text(encoding="utf-8", errors="ignore").splitlines():
                if not line.strip():
                    continue
                try:
                    rec = json.loads(line)
                except Exception:
                    continue
                if not isinstance(rec, dict):
                    continue
                if cid and str(rec.get("component_id") or "") != cid:
                    continue
                rows.append(rec)
        rows = sorted(rows, key=lambda x: float(x.get("ts") or 0.0), reverse=True)[:limit]
        return {"status": "ok", "count": len(rows), "acks": rows}

    if action == "check_ack_timeouts":
        timeout_sec = max(5, int(req.get("timeout_sec") or 120))
        statuses = set(req.get("statuses") or ["active", "pending", "running"])
        now = _now_ts()
        pending: List[Dict[str, Any]] = []
        for node in [v for v in comps.values() if isinstance(v, dict)]:
            cid = str(node.get("component_id") or "")
            if not cid:
                continue
            st = str(node.get("status") or "active").strip().lower()
            if st not in statuses:
                continue
            last_ack = node.get("last_ack") if isinstance(node.get("last_ack"), dict) else {}
            last_ack_ts = float((last_ack or {}).get("ts") or 0.0)
            updated_at = float(node.get("updated_at") or 0.0)
            ref_ts = max(last_ack_ts, updated_at)
            age_sec = max(0, int(now - ref_ts))
            if ref_ts <= 0.0 or age_sec >= timeout_sec:
                pending.append(
                    {
                        "component_id": cid,
                        "status": st,
                        "age_sec": age_sec,
                        "last_ack_ts": last_ack_ts,
                        "updated_at": updated_at,
                        "retry_hint": {
                            "action": "update",
                            "component_id": cid,
                            "state": {"retry_needed": True, "ack_timeout_sec": timeout_sec},
                        },
                    }
                )
        pending = sorted(pending, key=lambda x: (-int(x.get("age_sec") or 0), str(x.get("component_id") or "")))
        return {"status": "ok", "timeout_sec": timeout_sec, "pending_count": len(pending), "pending_acks": pending[:500]}

    if action == "delete":
        cid = str(req.get("component_id") or "").strip()
        node = comps.get(cid)
        if not cid or not isinstance(node, dict):
            return {"status": "error", "error": "component not found"}
        node["status"] = "deleted"
        node["updated_at"] = _now_ts()
        node["version"] = int(node.get("version") or 1) + 1
        comps[cid] = node
        state["components"] = comps
        _save_json(path, state)
        _safe_emit_ui("ui_event", {"type": "remove_ui", "payload": {"component_id": cid}})
        return {"status": "ok", "deleted": True, "component_id": cid}

    # create/update
    cid = str(req.get("component_id") or "").strip()
    if action == "update":
        if not cid or cid not in comps:
            return {"status": "error", "error": "component not found for update"}
        node = dict(comps.get(cid) or {})
        node["props"] = {**dict(node.get("props") or {}), **dict(req.get("props") or {})}
        node["state"] = {**dict(node.get("state") or {}), **dict(req.get("state") or {})}
        node["updated_at"] = _now_ts()
        node["version"] = int(node.get("version") or 1) + 1
        comps[cid] = node
        state["components"] = comps
        _save_json(path, state)
        _safe_emit_ui("ui_event", {"type": "update_ui", "payload": node})
        return {"status": "ok", "updated": True, "component": node}

    if action == "transition":
        cid = str(req.get("component_id") or "").strip()
        target = str(req.get("status") or "").strip().lower()
        allowed = {"pending", "running", "done", "error", "active", "deleted"}
        if target not in allowed:
            return {"status": "error", "error": f"invalid status transition target: {target}"}
        node = comps.get(cid)
        if not cid or not isinstance(node, dict):
            return {"status": "error", "error": "component not found for transition"}
        current = str(node.get("status") or "active").strip().lower()
        allow_force = bool(req.get("force", False))
        edges: Dict[str, set[str]] = {
            "active": {"pending", "running", "deleted", "error"},
            "pending": {"running", "error", "deleted"},
            "running": {"done", "error", "deleted"},
            "error": {"running", "deleted"},
            "done": {"active", "deleted"},
            "deleted": set(),
        }
        if target != current and (not allow_force) and target not in edges.get(current, set()):
            return {"status": "error", "error": f"invalid transition edge: {current} -> {target}"}
        node["status"] = target
        node["state"] = {**dict(node.get("state") or {}), **dict(req.get("state") or {})}
        node["updated_at"] = _now_ts()
        node["version"] = int(node.get("version") or 1) + 1
        node["last_transition"] = {"from": current, "to": target, "ts": _now_ts(), "forced": allow_force}
        comps[cid] = node
        state["components"] = comps
        _save_json(path, state)
        _safe_emit_ui("ui_event", {"type": "transition_ui", "payload": node})
        return {"status": "ok", "transitioned": True, "component": node}

    # create
    ctype = str(req.get("type") or "ActionCard").strip()
    props = dict(req.get("props") or {})
    cstate = dict(req.get("state") or {})
    cid = cid or f"comp_{uuid.uuid4().hex[:8]}"
    node = {
        "component_id": cid,
        "type": ctype,
        "props": props,
        "state": cstate,
        "status": "active",
        "version": 1,
        "created_at": _now_ts(),
        "updated_at": _now_ts(),
    }
    comps[cid] = node
    state["components"] = comps
    _save_json(path, state)
    _safe_emit_ui("ui_event", {"type": "render_ui", "payload": node})
    return {"status": "ok", "created": True, "component": node}


def tts_tool(req: Dict[str, Any], ctx: Any = None) -> Dict[str, Any]:
    text = str(req.get("text") or "").strip()
    if not text:
        return {"status": "error", "error": "text is required"}
    root = _repo_root_from_ctx(ctx)
    out_path = str(req.get("output_path") or str(root / "data" / "tts" / f"tts_{int(_now_ts())}.txt"))
    p = Path(out_path).expanduser().resolve()
    p.parent.mkdir(parents=True, exist_ok=True)
    wrote_audio = False
    try:
        import pyttsx3  # type: ignore

        engine = pyttsx3.init()
        wav_path = p.with_suffix(".wav")
        engine.save_to_file(text, str(wav_path))
        engine.runAndWait()
        wrote_audio = wav_path.exists()
        if wrote_audio:
            return {"status": "ok", "output_path": str(wav_path), "audio": True}
    except Exception:
        wrote_audio = False
    p.write_text(text, encoding="utf-8")
    return {"status": "ok", "output_path": str(p), "audio": wrote_audio, "fallback": "text_written"}


def agents_list_tool(req: Dict[str, Any], ctx: Any = None) -> Dict[str, Any]:
    root = _repo_root_from_ctx(ctx)
    sub_file = root / "data" / "subagent_status.json"
    data = _load_json(sub_file, {})
    agents: List[Dict[str, Any]] = []
    if isinstance(data, dict):
        for sid, v in data.items():
            if isinstance(v, dict):
                agents.append(
                    {
                        "session_id": sid,
                        "label": str(v.get("label") or ""),
                        "status": str(v.get("status") or "unknown"),
                        "model": str(v.get("model") or ""),
                        "parent_session_id": str(v.get("parent_session_id") or ""),
                    }
                )
    return {"status": "ok", "count": len(agents), "agents": agents}


def nodes_tool(req: Dict[str, Any], ctx: Any = None) -> Dict[str, Any]:
    root = _repo_root_from_ctx(ctx)
    path = root / "data" / "nodes_registry.json"
    assign_path = root / "data" / "node_assignments.json"
    lease_path = root / "data" / "nodes_leases.json"
    lease_events_path = root / "data" / "metrics" / "lease_events.jsonl"
    action = str(req.get("action") or "list").strip().lower()
    data = _load_json(path, {"nodes": []})
    assignments = _load_json(assign_path, {"assignments": [], "history": []})
    leases_data = _load_json(lease_path, {"leases": {}})
    if not isinstance(leases_data, dict):
        leases_data = {"leases": {}}
    if not isinstance(leases_data.get("leases"), dict):
        leases_data["leases"] = {}
    if not isinstance(assignments, dict):
        assignments = {"assignments": [], "history": []}
    if not isinstance(assignments.get("assignments"), list):
        assignments["assignments"] = []
    if not isinstance(assignments.get("history"), list):
        assignments["history"] = []
    assign_rows: List[Dict[str, Any]] = [x for x in assignments.get("assignments") or [] if isinstance(x, dict)]
    assign_history: List[Dict[str, Any]] = [x for x in assignments.get("history") or [] if isinstance(x, dict)]
    nodes = data.get("nodes") if isinstance(data, dict) else []
    if not isinstance(nodes, list):
        nodes = []
    now = _now_ts()
    raw_ttl = req.get("ttl_sec")
    try:
        ttl_sec = int(300 if raw_ttl is None else raw_ttl)
    except Exception:
        ttl_sec = 300
    normalized_nodes: List[Dict[str, Any]] = []
    for n in nodes:
        if not isinstance(n, dict):
            continue
        node = dict(n)
        hb = float(node.get("heartbeat_ts") or node.get("updated_at") or 0.0)
        node["heartbeat_ts"] = hb
        node["is_stale"] = bool(hb > 0 and (now - hb) > ttl_sec)
        normalized_nodes.append(node)
    nodes = normalized_nodes
    def _record_lease_event(kind: str, **payload: Any) -> None:
        _append_jsonl(
            lease_events_path,
            {
                "ts": _now_ts(),
                "kind": str(kind or "unknown"),
                **dict(payload or {}),
            },
        )

    def _effective_lease_ttl(base_ttl: int) -> int:
        b = max(5, int(base_ttl or 120))
        jitter = max(0, int(req.get("lease_jitter_sec") or 0))
        if jitter <= 0:
            return b
        delta = random.randint(-jitter, jitter)
        return max(5, b + delta)
    if action == "list":
        try:
            from quentin.infra.network.discovery import discovery

            ds = discovery.get_status()
        except Exception:
            ds = {}
        stale_count = sum(1 for n in nodes if bool(n.get("is_stale")))
        return {
            "status": "ok",
            "nodes": nodes,
            "count": len(nodes),
            "stale_count": stale_count,
            "ttl_sec": ttl_sec,
            "discovery": ds,
            "assignment_count": len(assign_rows),
            "assignment_history_count": len(assign_history),
            "lease_count": len(dict(leases_data.get("leases") or {})),
        }
    if action == "acquire_lease":
        lease_key = str(req.get("lease_key") or req.get("task_id") or "").strip()
        node_id = str(req.get("node_id") or "").strip()
        ttl_sec = _effective_lease_ttl(int(req.get("lease_ttl_sec") or 120))
        if not lease_key:
            return {"status": "error", "error": "lease_key required"}
        if not node_id:
            return {"status": "error", "error": "node_id required"}
        from quentin.runtime.session_write_lock import acquire_session_write_lock

        hold = acquire_session_write_lock(session_file=lease_path, timeout_ms=1500, stale_ms=30_000)
        try:
            fresh = _load_json(lease_path, {"leases": {}})
            if not isinstance(fresh, dict):
                fresh = {"leases": {}}
            leases = fresh.get("leases")
            if not isinstance(leases, dict):
                leases = {}
            now = _now_ts()
            rec = leases.get(lease_key) if isinstance(leases.get(lease_key), dict) else None
            owner = str((rec or {}).get("node_id") or "")
            exp = float((rec or {}).get("expires_at") or 0.0)
            if rec and owner and owner != node_id and exp > now:
                _record_lease_event(
                    "acquire_blocked",
                    action="acquire_lease",
                    lease_key=lease_key,
                    node_id=node_id,
                    owner_node_id=owner,
                    reason="owner_alive",
                )
                return {"status": "ok", "acquired": False, "lease_key": lease_key, "owner_node_id": owner, "expires_at": exp}
            new_rec = {"lease_key": lease_key, "node_id": node_id, "acquired_at": now, "expires_at": now + ttl_sec, "lease_ttl_sec": ttl_sec}
            leases[lease_key] = new_rec
            fresh["leases"] = leases
            _save_json(lease_path, fresh)
            _record_lease_event("acquired", action="acquire_lease", lease_key=lease_key, node_id=node_id, lease_ttl_sec=ttl_sec)
            return {"status": "ok", "acquired": True, "lease": new_rec}
        finally:
            hold["release"]()
    if action == "renew_lease":
        lease_key = str(req.get("lease_key") or req.get("task_id") or "").strip()
        node_id = str(req.get("node_id") or "").strip()
        ttl_sec = _effective_lease_ttl(int(req.get("lease_ttl_sec") or 120))
        expected_epoch = req.get("expected_epoch")
        if not lease_key:
            return {"status": "error", "error": "lease_key required"}
        if not node_id:
            return {"status": "error", "error": "node_id required"}
        from quentin.runtime.session_write_lock import acquire_session_write_lock

        hold = acquire_session_write_lock(session_file=lease_path, timeout_ms=1500, stale_ms=30_000)
        try:
            fresh = _load_json(lease_path, {"leases": {}})
            if not isinstance(fresh, dict):
                fresh = {"leases": {}}
            leases = fresh.get("leases")
            if not isinstance(leases, dict):
                leases = {}
            now = _now_ts()
            rec = leases.get(lease_key) if isinstance(leases.get(lease_key), dict) else None
            if not rec:
                _record_lease_event("renew_miss", action="renew_lease", lease_key=lease_key, node_id=node_id, reason="not_found")
                return {"status": "ok", "renewed": False, "reason": "not_found", "lease_key": lease_key}
            owner = str((rec or {}).get("node_id") or "")
            exp = float((rec or {}).get("expires_at") or 0.0)
            if owner != node_id and exp > now:
                _record_lease_event(
                    "renew_blocked",
                    action="renew_lease",
                    lease_key=lease_key,
                    node_id=node_id,
                    owner_node_id=owner,
                    reason="owner_mismatch",
                )
                return {"status": "ok", "renewed": False, "reason": "owner_mismatch", "lease_key": lease_key, "owner_node_id": owner}
            if expected_epoch is not None:
                try:
                    ee = int(expected_epoch)
                except Exception:
                    ee = -1
                cur_epoch = int((rec or {}).get("epoch") or 0)
                if ee != cur_epoch:
                    _record_lease_event(
                        "fencing_conflict",
                        action="renew_lease",
                        lease_key=lease_key,
                        node_id=node_id,
                        expected_epoch=ee,
                        current_epoch=cur_epoch,
                    )
                    return {
                        "status": "ok",
                        "renewed": False,
                        "reason": "fenced_out",
                        "lease_key": lease_key,
                        "expected_epoch": ee,
                        "current_epoch": cur_epoch,
                    }
            new_rec = {
                **dict(rec),
                "node_id": node_id,
                "renewed_at": now,
                "expires_at": now + ttl_sec,
                "lease_ttl_sec": ttl_sec,
            }
            leases[lease_key] = new_rec
            fresh["leases"] = leases
            _save_json(lease_path, fresh)
            _record_lease_event(
                "renewed",
                action="renew_lease",
                lease_key=lease_key,
                node_id=node_id,
                epoch=int(new_rec.get("epoch") or 0),
                lease_ttl_sec=ttl_sec,
            )
            return {"status": "ok", "renewed": True, "lease": new_rec}
        finally:
            hold["release"]()
    if action == "elect_leader":
        group_key = str(req.get("group_key") or "default").strip()
        node_id = str(req.get("node_id") or "").strip()
        priority = int(req.get("priority") or 0)
        ttl_sec = _effective_lease_ttl(int(req.get("lease_ttl_sec") or 120))
        quorum = max(1, int(req.get("quorum") or 1))
        expected_epoch = req.get("expected_epoch")
        if not node_id:
            return {"status": "error", "error": "node_id required"}
        lease_key = f"leader::{group_key}"
        healthy_nodes = [n for n in nodes if not bool(n.get("is_stale")) and str(n.get("status") or "online") in {"online", "ready"}]
        healthy_ids = {str(n.get("node_id") or "") for n in healthy_nodes}
        healthy_count = len(healthy_nodes)
        # Backward-compatible behavior: if registry has no self record, treat caller as one healthy voter.
        if node_id and node_id not in healthy_ids:
            healthy_count += 1
        if healthy_count < quorum:
            _record_lease_event(
                "quorum_not_met",
                action="elect_leader",
                group_key=group_key,
                node_id=node_id,
                quorum=quorum,
                healthy_nodes=healthy_count,
            )
            return {
                "status": "ok",
                "elected": False,
                "reason": "quorum_not_met",
                "healthy_nodes": healthy_count,
                "quorum": quorum,
                "lease_key": lease_key,
            }
        from quentin.runtime.session_write_lock import acquire_session_write_lock

        hold = acquire_session_write_lock(session_file=lease_path, timeout_ms=1500, stale_ms=30_000)
        try:
            fresh = _load_json(lease_path, {"leases": {}})
            if not isinstance(fresh, dict):
                fresh = {"leases": {}}
            leases = fresh.get("leases")
            if not isinstance(leases, dict):
                leases = {}
            now = _now_ts()
            rec = leases.get(lease_key) if isinstance(leases.get(lease_key), dict) else None
            current_epoch = int((rec or {}).get("epoch") or 0)
            if expected_epoch is not None:
                try:
                    ee = int(expected_epoch)
                except Exception:
                    ee = -1
                if ee != current_epoch:
                    _record_lease_event(
                        "fencing_conflict",
                        action="elect_leader",
                        lease_key=lease_key,
                        group_key=group_key,
                        node_id=node_id,
                        expected_epoch=ee,
                        current_epoch=current_epoch,
                    )
                    return {
                        "status": "ok",
                        "elected": False,
                        "reason": "fenced_out",
                        "lease_key": lease_key,
                        "expected_epoch": ee,
                        "current_epoch": current_epoch,
                    }
            if rec:
                owner = str(rec.get("node_id") or "")
                exp = float(rec.get("expires_at") or 0.0)
                op = int(rec.get("priority") or 0)
                if exp > now and owner and owner != node_id and op > priority:
                    _record_lease_event(
                        "leader_blocked_higher_priority",
                        action="elect_leader",
                        lease_key=lease_key,
                        group_key=group_key,
                        node_id=node_id,
                        owner_node_id=owner,
                        owner_priority=op,
                        priority=priority,
                    )
                    return {
                        "status": "ok",
                        "elected": False,
                        "leader_node_id": owner,
                        "lease_key": lease_key,
                        "reason": "higher_priority_owner",
                    }
                if exp > now and owner == node_id:
                    new_leader = {
                        **dict(rec),
                        "priority": priority,
                        "renewed_at": now,
                        "expires_at": now + ttl_sec,
                        "lease_ttl_sec": ttl_sec,
                        "quorum": quorum,
                    }
                    leases[lease_key] = new_leader
                    fresh["leases"] = leases
                    _save_json(lease_path, fresh)
                    _record_lease_event(
                        "leader_renewed",
                        action="elect_leader",
                        lease_key=lease_key,
                        group_key=group_key,
                        node_id=node_id,
                        epoch=int(new_leader.get("epoch") or 0),
                        lease_ttl_sec=ttl_sec,
                    )
                    return {
                        "status": "ok",
                        "elected": True,
                        "leader_node_id": node_id,
                        "lease": new_leader,
                        "reused_epoch": True,
                    }
            next_epoch = current_epoch + 1
            leader = {
                "lease_key": lease_key,
                "group_key": group_key,
                "node_id": node_id,
                "priority": priority,
                "elected_at": now,
                "expires_at": now + ttl_sec,
                "lease_ttl_sec": ttl_sec,
                "quorum": quorum,
                "epoch": next_epoch,
                "fencing_token": f"{group_key}:{next_epoch}:{node_id}",
            }
            leases[lease_key] = leader
            fresh["leases"] = leases
            _save_json(lease_path, fresh)
            _record_lease_event(
                "leader_elected",
                action="elect_leader",
                lease_key=lease_key,
                group_key=group_key,
                node_id=node_id,
                epoch=int(leader.get("epoch") or 0),
                fencing_token=str(leader.get("fencing_token") or ""),
                quorum=quorum,
                lease_ttl_sec=ttl_sec,
            )
            return {"status": "ok", "elected": True, "leader_node_id": node_id, "lease": leader}
        finally:
            hold["release"]()
    if action == "release_lease":
        lease_key = str(req.get("lease_key") or req.get("task_id") or "").strip()
        node_id = str(req.get("node_id") or "").strip()
        if not lease_key:
            return {"status": "error", "error": "lease_key required"}
        from quentin.runtime.session_write_lock import acquire_session_write_lock

        hold = acquire_session_write_lock(session_file=lease_path, timeout_ms=1500, stale_ms=30_000)
        try:
            fresh = _load_json(lease_path, {"leases": {}})
            if not isinstance(fresh, dict):
                fresh = {"leases": {}}
            leases = fresh.get("leases")
            if not isinstance(leases, dict):
                leases = {}
            rec = leases.get(lease_key) if isinstance(leases.get(lease_key), dict) else None
            if not rec:
                return {"status": "ok", "released": False, "reason": "not_found", "lease_key": lease_key}
            owner = str((rec or {}).get("node_id") or "")
            if node_id and owner and owner != node_id:
                return {"status": "ok", "released": False, "reason": "owner_mismatch", "lease_key": lease_key, "owner_node_id": owner}
            leases.pop(lease_key, None)
            fresh["leases"] = leases
            _save_json(lease_path, fresh)
            return {"status": "ok", "released": True, "lease_key": lease_key}
        finally:
            hold["release"]()
    if action == "lease_status":
        lease_key = str(req.get("lease_key") or "").strip()
        leases = dict(leases_data.get("leases") or {})
        now = _now_ts()
        if lease_key:
            rec = leases.get(lease_key) if isinstance(leases.get(lease_key), dict) else None
            if not rec:
                return {"status": "ok", "lease_key": lease_key, "exists": False}
            return {
                "status": "ok",
                "lease_key": lease_key,
                "exists": True,
                "lease": rec,
                "is_expired": float(rec.get("expires_at") or 0.0) <= now,
            }
        rows = [v for v in leases.values() if isinstance(v, dict)]
        rows = sorted(rows, key=lambda x: float(x.get("expires_at") or 0.0), reverse=True)
        return {"status": "ok", "count": len(rows), "leases": rows[:500]}
    if action == "list_assignments":
        return {"status": "ok", "assignments": assign_rows, "count": len(assign_rows)}
    if action == "assignment_history":
        limit = max(1, min(500, int(req.get("limit") or 200)))
        rows = sorted(assign_history, key=lambda x: float(x.get("released_at") or x.get("assigned_at") or 0.0), reverse=True)[:limit]
        return {"status": "ok", "history": rows, "count": len(rows)}
    if action == "assign_task":
        task_id = str(req.get("task_id") or "").strip()
        if not task_id:
            return {"status": "error", "error": "task_id required"}
        node_id = str(req.get("node_id") or "").strip()
        if not node_id:
            # pick least-loaded healthy node
            loads: Dict[str, int] = {}
            for a in assign_rows:
                nid = str(a.get("node_id") or "")
                if nid:
                    loads[nid] = loads.get(nid, 0) + 1
            candidates = [n for n in nodes if not bool(n.get("is_stale")) and str(n.get("status") or "online") in {"online", "ready"} and str(n.get("node_id") or "")]
            if not candidates:
                return {"status": "error", "error": "no healthy nodes available"}
            candidates = sorted(candidates, key=lambda n: (loads.get(str(n.get("node_id") or ""), 0), str(n.get("node_id") or "")))
            node_id = str(candidates[0].get("node_id") or "")
        from quentin.runtime.session_write_lock import acquire_session_write_lock

        hold = acquire_session_write_lock(session_file=assign_path, timeout_ms=1500, stale_ms=30_000)
        try:
            fresh = _load_json(assign_path, {"assignments": [], "history": []})
            if not isinstance(fresh, dict):
                fresh = {"assignments": [], "history": []}
            fr = [x for x in list(fresh.get("assignments") or []) if isinstance(x, dict)]
            rec = {
                "task_id": task_id,
                "node_id": node_id,
                "assigned_at": now,
                "status": str(req.get("status") or "assigned"),
                "meta": dict(req.get("meta") or {}),
            }
            fr = [a for a in fr if str(a.get("task_id") or "") != task_id]
            fr.append(rec)
            fresh["assignments"] = fr
            if not isinstance(fresh.get("history"), list):
                fresh["history"] = []
            _save_json(assign_path, fresh)
            return {"status": "ok", "assigned": rec}
        finally:
            hold["release"]()
    if action == "release_task":
        task_id = str(req.get("task_id") or "").strip()
        if not task_id:
            return {"status": "error", "error": "task_id required"}
        final_status = str(req.get("final_status") or "").strip().lower()
        reason = str(req.get("release_reason") or req.get("source") or "manual_release").strip()
        from quentin.runtime.session_write_lock import acquire_session_write_lock

        hold = acquire_session_write_lock(session_file=assign_path, timeout_ms=1500, stale_ms=30_000)
        try:
            fresh = _load_json(assign_path, {"assignments": [], "history": []})
            if not isinstance(fresh, dict):
                fresh = {"assignments": [], "history": []}
            fr = [x for x in list(fresh.get("assignments") or []) if isinstance(x, dict)]
            fh = [x for x in list(fresh.get("history") or []) if isinstance(x, dict)]
            kept: List[Dict[str, Any]] = []
            removed_rows: List[Dict[str, Any]] = []
            for a in fr:
                if str(a.get("task_id") or "") == task_id:
                    row = dict(a)
                    row["released_at"] = now
                    row["release_reason"] = reason
                    if final_status:
                        row["final_status"] = final_status
                    fh.append(row)
                    removed_rows.append(row)
                else:
                    kept.append(a)
            before = len(fr)
            fresh["assignments"] = kept
            fresh["history"] = fh[-2000:]
            _save_json(assign_path, fresh)
            return {"status": "ok", "released": task_id, "removed": before - len(kept), "records": removed_rows[:20]}
        finally:
            hold["release"]()
    if action == "reconcile_assignments":
        from quentin.runtime.session_write_lock import acquire_session_write_lock

        hold = acquire_session_write_lock(session_file=assign_path, timeout_ms=1500, stale_ms=30_000)
        try:
            fresh = _load_json(assign_path, {"assignments": [], "history": []})
            if not isinstance(fresh, dict):
                fresh = {"assignments": [], "history": []}
            assign_rows = [x for x in list(fresh.get("assignments") or []) if isinstance(x, dict)]
            assign_history = [x for x in list(fresh.get("history") or []) if isinstance(x, dict)]
            try:
                from quentin.runtime.task_queue import TaskQueue

                q = TaskQueue(repo_root=str(root))
                qitems = q.load_all(limit=5000)
            except Exception as e:
                return {"status": "error", "error": f"failed to load task queue: {e}"}
            status_by_task: Dict[str, str] = {}
            for it in qitems:
                tid = str(getattr(it, "task_id", "") or "")
                if not tid:
                    continue
                status_by_task[tid] = str(getattr(it, "status", "") or "")
            stale_node_ids = {str(n.get("node_id") or "") for n in nodes if bool(n.get("is_stale")) and str(n.get("node_id") or "")}
            healthy_nodes = [
                n
                for n in nodes
                if not bool(n.get("is_stale")) and str(n.get("status") or "online") in {"online", "ready"} and str(n.get("node_id") or "")
            ]
            migrate_stale = bool(req.get("migrate_stale_assignments", True))
            kept: List[Dict[str, Any]] = []
            released: List[Dict[str, Any]] = []
            migrated: List[Dict[str, Any]] = []
            loads: Dict[str, int] = {}
            for a in assign_rows:
                nid = str(a.get("node_id") or "")
                if nid:
                    loads[nid] = loads.get(nid, 0) + 1
            for a in assign_rows:
                tid = str(a.get("task_id") or "")
                st = status_by_task.get(tid, "")
                if st in {"done", "failed"}:
                    row = dict(a)
                    row["released_at"] = now
                    row["release_reason"] = f"task_{st}"
                    row["final_status"] = st
                    assign_history.append(row)
                    released.append(row)
                    old_nid = str(a.get("node_id") or "")
                    if old_nid:
                        loads[old_nid] = max(0, loads.get(old_nid, 0) - 1)
                    continue
                nid = str(a.get("node_id") or "")
                if nid and nid in stale_node_ids:
                    row = dict(a)
                    row["released_at"] = now
                    row["release_reason"] = "node_stale"
                    assign_history.append(row)
                    released.append(row)
                    if nid:
                        loads[nid] = max(0, loads.get(nid, 0) - 1)
                    if migrate_stale and st in {"pending", ""} and healthy_nodes:
                        healthy_nodes = sorted(
                            healthy_nodes,
                            key=lambda n: (loads.get(str(n.get("node_id") or ""), 0), str(n.get("node_id") or "")),
                        )
                        new_nid = str(healthy_nodes[0].get("node_id") or "")
                        if new_nid:
                            rec = {
                                "task_id": tid,
                                "node_id": new_nid,
                                "assigned_at": now,
                                "status": "assigned",
                                "meta": {
                                    "migrated_from": nid,
                                    "migration_reason": "node_stale",
                                },
                            }
                            kept.append(rec)
                            migrated.append(rec)
                            loads[new_nid] = loads.get(new_nid, 0) + 1
                else:
                    kept.append(a)
            assign_rows = kept

            auto_assign = bool(req.get("auto_assign_pending", False))
            assigned_new: List[Dict[str, Any]] = []
            if auto_assign:
                assigned_task_ids = {str(a.get("task_id") or "") for a in assign_rows}
                candidates = list(healthy_nodes)
                for a in assign_rows:
                    nid = str(a.get("node_id") or "")
                    if nid:
                        loads[nid] = loads.get(nid, 0)
                for it in qitems:
                    tid = str(getattr(it, "task_id", "") or "")
                    st = str(getattr(it, "status", "") or "")
                    if not tid or st != "pending" or tid in assigned_task_ids:
                        continue
                    if not candidates:
                        break
                    candidates = sorted(candidates, key=lambda n: (loads.get(str(n.get("node_id") or ""), 0), str(n.get("node_id") or "")))
                    nid = str(candidates[0].get("node_id") or "")
                    rec = {
                        "task_id": tid,
                        "node_id": nid,
                        "assigned_at": now,
                        "status": "assigned",
                        "meta": {"auto_assigned": True},
                    }
                    assign_rows.append(rec)
                    assigned_new.append(rec)
                    loads[nid] = loads.get(nid, 0) + 1
                    assigned_task_ids.add(tid)

            if len(assign_history) > 5000:
                assign_history = assign_history[-2000:]
            fresh["assignments"] = assign_rows
            fresh["history"] = assign_history
            _save_json(assign_path, fresh)
            return {
                "status": "ok",
                "active_count": len(assign_rows),
                "history_count": len(assign_history),
                "released_count": len(released),
                "released": released[:200],
                "migrated_count": len(migrated),
                "migrated": migrated[:200],
                "new_assigned_count": len(assigned_new),
                "new_assigned": assigned_new[:200],
            }
        finally:
            hold["release"]()
    if action == "advertise":
        port = int(req.get("port") or 8000)
        try:
            from quentin.infra.network.discovery import discovery

            discovery.advertise_service(port)
            ds = discovery.get_status()
        except Exception as e:
            return {"status": "error", "error": str(e)}
        return {"status": "ok", "advertised": True, "discovery": ds}
    if action == "stop_advertise":
        try:
            from quentin.infra.network.discovery import discovery

            discovery.stop()
            ds = discovery.get_status()
        except Exception as e:
            return {"status": "error", "error": str(e)}
        return {"status": "ok", "advertised": False, "discovery": ds}
    if action == "heartbeat":
        node_id = str(req.get("node_id") or "").strip()
        host = str(req.get("host") or "").strip()
        if not node_id:
            return {"status": "error", "error": "node_id required"}
        found = False
        for n in nodes:
            if str(n.get("node_id") or "") == node_id:
                n["heartbeat_ts"] = now
                n["updated_at"] = now
                if host:
                    n["host"] = host
                n["status"] = str(req.get("status") or n.get("status") or "online")
                found = True
                break
        if not found:
            nodes.append(
                {
                    "node_id": node_id,
                    "host": host,
                    "status": str(req.get("status") or "online"),
                    "updated_at": now,
                    "heartbeat_ts": now,
                    "is_stale": False,
                }
            )
        _save_json(path, {"nodes": nodes})
        return {"status": "ok", "heartbeat": True, "node_id": node_id}
    if action == "purge_stale":
        kept = [n for n in nodes if not bool(n.get("is_stale"))]
        purged = len(nodes) - len(kept)
        _save_json(path, {"nodes": kept})
        return {"status": "ok", "purged": purged, "remaining": len(kept), "ttl_sec": ttl_sec}
    if action == "upsert":
        node_id = str(req.get("node_id") or "").strip()
        host = str(req.get("host") or "").strip()
        if not node_id:
            return {"status": "error", "error": "node_id required"}
        found = False
        for n in nodes:
            if isinstance(n, dict) and str(n.get("node_id") or "") == node_id:
                n.update(
                    {
                        "host": host or n.get("host"),
                        "updated_at": now,
                        "heartbeat_ts": now,
                        "status": str(req.get("status") or "online"),
                        "is_stale": False,
                    }
                )
                found = True
                break
        if not found:
            nodes.append(
                {
                    "node_id": node_id,
                    "host": host,
                    "status": str(req.get("status") or "online"),
                    "updated_at": now,
                    "heartbeat_ts": now,
                    "is_stale": False,
                }
            )
        data = {"nodes": nodes}
        _save_json(path, data)
        return {"status": "ok", "upserted": node_id, "count": len(nodes)}
    return {"status": "error", "error": f"unknown action: {action}"}


def tool_specs() -> List[Tuple[str, str, str, Dict[str, Any]]]:
    return [
        ("agent.step", "Single-step execution wrapper with retry/error classification.", "ops", {"tags": ["execution", "retry"]}),
        ("gateway.tool", "Gateway messaging entrypoint (status/inbound/outbound/providers).", "communication", {"tags": ["gateway", "messaging"]}),
        ("message.tool", "Unified cross-platform messaging tool (send/thread/edit/delete/react).", "communication", {"tags": ["messaging", "unified"]}),
        ("discord.actions", "Discord message/channel action tool (webhook-first).", "communication", {"tags": ["messaging"]}),
        ("slack.actions", "Slack team communication action tool (webhook-first).", "communication", {"tags": ["messaging"]}),
        ("telegram.actions", "Telegram messaging action tool.", "communication", {"tags": ["messaging"]}),
        ("whatsapp.actions", "WhatsApp messaging action tool.", "communication", {"tags": ["messaging"]}),
        ("channels.listener", "Start/stop/poll inbound listener for communication channels.", "communication", {"tags": ["messaging", "listener"]}),
        ("cron.tool", "Schedule/list/remove recurring tasks using cron-like syntax.", "ops", {}),
        ("session.status", "Inspect multi-session runtime health and active locks.", "ops", {}),
        ("sessions.announce_target", "Announce target objective across sessions.", "ops", {}),
        ("sessions.list", "List known sessions (locks, tasks, events, subagents).", "ops", {}),
        ("sessions.history", "Inspect a session's recent queue/events/handoffs.", "ops", {}),
        ("sessions.send", "Send a message/task to a session (system_event or task_queue).", "ops", {}),
        ("sessions.spawn", "Spawn an isolated session by enqueuing its first task.", "ops", {}),
        ("web.readability", "Extract readable text from noisy HTML/web pages.", "web", {}),
        ("web.fetch", "Fetch a URL with SSRF guard and extract text/markdown.", "web", {}),
        ("web.search", "Search web results (offline corpus/mock provider supported).", "web", {}),
        ("memory.search", "Search MEMORY.md/memory/docs for prior decisions and todos.", "memory", {}),
        ("memory.get", "Safe snippet read from MEMORY.md/memory/docs.", "memory", {}),
        ("image.tool", "Image OCR/compression/feature extraction utility.", "media", {}),
        ("tts.tool", "Text-to-speech output tool with local fallback.", "media", {}),
        ("canvas.tool", "Canvas component lifecycle management (create/update/delete/list/get).", "media", {}),
        ("agents.list", "List active sub-agents and their runtime status.", "meta", {}),
        ("nodes.tool", "Distributed node status management.", "meta", {}),
    ]
