from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from quentin.tools.execution_parity import agent_step_tool, gateway_tool


def _ctx(root: Path):
    return SimpleNamespace(metadata={"repo_root": str(root)})


def test_gateway_tool_status_and_inbound(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    st = gateway_tool({"action": "status"}, ctx)
    assert st["status"] in {"ok", "error"}

    inbound = gateway_tool(
        {
            "action": "inbound",
            "platform": "discord",
            "text": "hello",
            "metadata": {"channel_id": "g1"},
        },
        ctx,
    )
    assert inbound["status"] in {"accepted", "error"}


def test_gateway_tool_outbound_uses_message_tool(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    out = gateway_tool(
        {
            "action": "outbound",
            "platform": "discord",
            "channel_id": "g2",
            "text": "agent hello",
            "dry_run": True,
        },
        ctx,
    )
    assert out["status"] == "ok"
    assert out["platform"] == "discord"
    assert out.get("tool") == "gateway.tool"


def test_gateway_tool_outbound_idempotency_dedupes(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    first = gateway_tool(
        {
            "action": "outbound",
            "platform": "discord",
            "channel_id": "g3",
            "text": "agent hello",
            "dry_run": True,
            "idempotency_key": "gw-idem-1",
        },
        ctx,
    )
    second = gateway_tool(
        {
            "action": "outbound",
            "platform": "discord",
            "channel_id": "g3",
            "text": "agent hello",
            "dry_run": True,
            "idempotency_key": "gw-idem-1",
        },
        ctx,
    )
    assert first["status"] == "ok"
    assert second["status"] == "ok"
    assert bool(second.get("deduped")) is True


def test_agent_step_tool_execute_and_retry(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    ok = agent_step_tool(
        {
            "action": "execute",
            "tool": "web.search",
            "args": {
                "query": "openai quickstart",
                "max_results": 3,
                "corpus": [
                    {"title": "OpenAI Quickstart", "url": "https://example.com/1", "snippet": "openai api"},
                    {"title": "Cron", "url": "https://example.com/2", "snippet": "cron schedule"},
                ],
            },
            "max_retries": 1,
        },
        ctx,
    )
    assert ok["status"] == "ok"
    assert ok["tool"] == "web.search"
    assert ok["attempt_count"] >= 1


def test_agent_step_tool_rejects_unknown_tool(tmp_path: Path) -> None:
    out = agent_step_tool({"action": "execute", "tool": "nope.tool", "args": {}}, _ctx(tmp_path))
    assert out["status"] == "error"
