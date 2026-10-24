from __future__ import annotations

import json
from types import SimpleNamespace

from quentin.tools.execution_parity import channels_listener_tool


def _load_thread(tmp_path, platform: str, thread_id: str):
    path = tmp_path / "data" / "channels" / f"{platform}_threads.json"
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    node = ((data or {}).get("threads") or {}).get(thread_id) or {}
    return list(node.get("messages") or [])


def test_channels_listener_inject_dedupe_edit_delete_and_auto_reply(tmp_path) -> None:
    ctx = SimpleNamespace(metadata={"repo_root": str(tmp_path.resolve())})

    channels_listener_tool({"action": "clear_dead_letters"}, ctx)

    r1 = channels_listener_tool(
        {
            "action": "inject",
            "platform": "discord",
            "text": "hello",
            "sender_id": "u1",
            "message_id": "m1",
            "metadata": {"channel_id": "c1"},
            "auto_reply": True,
            "auto_reply_mode": "template",
            "auto_reply_template": "ACK:{text}",
            "auto_reply_send": False,
        },
        ctx,
    )
    assert r1.get("status") == "ok"
    assert r1.get("thread_id") == "discord:c1"
    assert bool(r1.get("deduped")) is False

    rdup = channels_listener_tool(
        {
            "action": "inject",
            "platform": "discord",
            "text": "hello",
            "sender_id": "u1",
            "message_id": "m1",
            "metadata": {"channel_id": "c1"},
            "auto_reply": True,
            "auto_reply_mode": "template",
            "auto_reply_template": "ACK:{text}",
            "auto_reply_send": False,
        },
        ctx,
    )
    assert bool(rdup.get("deduped")) is True

    _ = channels_listener_tool(
        {
            "action": "inject",
            "platform": "discord",
            "text": "world",
            "sender_id": "u2",
            "message_id": "m2",
            "metadata": {"channel_id": "c1"},
            "auto_reply": True,
            "auto_reply_mode": "template",
            "auto_reply_template": "ACK:{text}",
            "auto_reply_send": False,
        },
        ctx,
    )

    _ = channels_listener_tool(
        {
            "action": "inject",
            "platform": "discord",
            "text": "hello EDIT",
            "sender_id": "u1",
            "message_id": "m1",
            "event_kind": "edit",
            "metadata": {"channel_id": "c1"},
            "auto_reply": False,
        },
        ctx,
    )

    _ = channels_listener_tool(
        {
            "action": "inject",
            "platform": "discord",
            "text": "",
            "sender_id": "u2",
            "message_id": "m2",
            "event_kind": "delete",
            "metadata": {"channel_id": "c1"},
            "auto_reply": False,
        },
        ctx,
    )

    msgs = _load_thread(tmp_path, "discord", "discord:c1")
    assert len(msgs) == 4  # 2 user messages + 2 auto-replies
    assert sum(1 for m in msgs if str(m.get("role") or "") == "agent") == 2
    assert any("hello EDIT" in str(m.get("text") or "") for m in msgs)
    assert any(str(m.get("text") or "") == "[deleted]" for m in msgs)


def test_channels_listener_dead_letters_on_store_failure(tmp_path) -> None:
    ctx = SimpleNamespace(metadata={"repo_root": str(tmp_path.resolve())})

    bad_platform = "benchsim"
    bad_path = tmp_path / "data" / "channels" / f"{bad_platform}_threads.json"
    bad_path.parent.mkdir(parents=True, exist_ok=True)
    bad_path.mkdir()

    channels_listener_tool({"action": "clear_dead_letters", "platform": bad_platform}, ctx)
    _ = channels_listener_tool(
        {
            "action": "inject",
            "platform": bad_platform,
            "text": "x",
            "sender_id": "u",
            "message_id": "m1",
            "metadata": {"thread_id": "t1"},
            "auto_reply": False,
        },
        ctx,
    )
    dl = channels_listener_tool({"action": "dead_letters", "platform": bad_platform, "limit": 10}, ctx)
    assert int(dl.get("count") or 0) >= 1

    # Restore writable thread store and redrive dead letters.
    bad_path.rmdir()
    rd = channels_listener_tool({"action": "redrive_dead_letters", "platform": bad_platform, "limit": 10}, ctx)
    assert rd.get("status") == "ok"
    assert int(rd.get("replayed") or 0) >= 1

    dl2 = channels_listener_tool({"action": "dead_letters", "platform": bad_platform, "limit": 10}, ctx)
    assert int(dl2.get("count") or 0) == 0
