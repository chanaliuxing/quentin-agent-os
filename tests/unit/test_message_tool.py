from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

from quentin.tools.execution_parity import message_tool


def _ctx(root: Path):
    return SimpleNamespace(metadata={"repo_root": str(root)})


def test_message_tool_send_and_fetch_thread(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    sent = asyncio.run(
        message_tool(
            {
                "platform": "discord",
                "action": "send",
                "text": "hello",
                "channel_id": "c1",
                "dry_run": True,
            },
            ctx,
        )
    )
    assert sent["status"] == "ok"
    assert sent["platform"] == "discord"
    assert sent.get("routed_to") == "discord.actions"

    fetched = asyncio.run(
        message_tool(
            {
                "platform": "discord",
                "action": "fetch_thread",
                "thread_id": "discord:c1",
            },
            ctx,
        )
    )
    assert fetched["status"] == "ok"
    assert fetched["count"] >= 1


def test_message_tool_normalizes_telegram_channel_id(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    out = asyncio.run(
        message_tool(
            {
                "platform": "telegram",
                "action": "send",
                "text": "tg hi",
                "channel_id": "chat-1",
                "dry_run": True,
            },
            ctx,
        )
    )
    assert out["status"] == "ok"
    assert out["platform"] == "telegram"
    assert str(out.get("thread_id") or "").startswith("telegram:chat-1")


def test_message_tool_edit_delete_and_react(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    ingest = asyncio.run(
        message_tool(
            {
                "platform": "discord",
                "action": "ingest",
                "thread_id": "discord:t1",
                "text": "orig",
                "user_id": "u1",
                "meta": {"external_message_id": "m1"},
            },
            ctx,
        )
    )
    assert ingest["status"] == "ok"

    edited = asyncio.run(
        message_tool(
            {
                "platform": "discord",
                "action": "edit",
                "thread_id": "discord:t1",
                "message_id": "m1",
                "text": "edited",
                "user_id": "u1",
            },
            ctx,
        )
    )
    assert edited["status"] == "ok"
    assert edited["event"] == "edit"
    assert edited["applied"] is True

    reacted = asyncio.run(
        message_tool(
            {
                "platform": "discord",
                "action": "react",
                "thread_id": "discord:t1",
                "message_id": "m1",
                "emoji": ":thumbs_up:",
                "user_id": "u2",
            },
            ctx,
        )
    )
    assert reacted["status"] == "ok"
    assert reacted["event"] == "react"

    deleted = asyncio.run(
        message_tool(
            {
                "platform": "discord",
                "action": "delete",
                "thread_id": "discord:t1",
                "message_id": "m1",
                "user_id": "u1",
            },
            ctx,
        )
    )
    assert deleted["status"] == "ok"
    assert deleted["event"] == "delete"
    assert deleted["applied"] is True

    fetched = asyncio.run(
        message_tool(
            {
                "platform": "discord",
                "action": "fetch_thread",
                "thread_id": "discord:t1",
                "limit": 20,
            },
            ctx,
        )
    )
    texts = [str((m or {}).get("text") or "") for m in (fetched.get("messages") or [])]
    assert "[deleted]" in texts
    assert any("reaction" in t for t in texts)


def test_message_tool_rejects_unknown_platform() -> None:
    out = asyncio.run(message_tool({"platform": "email", "action": "send", "text": "x"}, None))
    assert out["status"] == "error"


def test_message_tool_idempotency_dedupes_send(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    first = asyncio.run(
        message_tool(
            {
                "platform": "discord",
                "action": "send",
                "text": "hello",
                "channel_id": "idem-c1",
                "dry_run": True,
                "idempotency_key": "msg-idem-1",
            },
            ctx,
        )
    )
    second = asyncio.run(
        message_tool(
            {
                "platform": "discord",
                "action": "send",
                "text": "hello",
                "channel_id": "idem-c1",
                "dry_run": True,
                "idempotency_key": "msg-idem-1",
            },
            ctx,
        )
    )
    assert first["status"] == "ok"
    assert second["status"] == "ok"
    assert second.get("deduped") is True
