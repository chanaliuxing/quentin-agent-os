from __future__ import annotations

import asyncio

import pytest

from quentin.infra.concurrency.cancellation import CancellationToken, CancelledError
from quentin.tools.manager import ToolCallContext, ToolManager, ToolPolicy
from quentin.tools.schemas import ToolCallRequest


def test_tool_pipeline_same_session_same_toolset_across_entrypoints() -> None:
    tm = ToolManager()
    tm.register("channel.send_text", lambda params: {"status": "ok", "params": params})
    tm.register("discord.send_message", lambda params: {"status": "ok", "params": params})

    base_md = {
        "session_id": "s1",
        "domain": "communication",
        "environment": "sandbox",
        "channel": "discord",
    }
    cli = dict(base_md, source="qctl")
    api = dict(base_md, source="api")
    daemon = dict(base_md, source="brain_daemon")

    cli_tools = set(tm.get_tool_summaries(max_words=8, context_metadata=cli).keys())
    api_tools = set(tm.get_tool_summaries(max_words=8, context_metadata=api).keys())
    daemon_tools = set(tm.get_tool_summaries(max_words=8, context_metadata=daemon).keys())

    assert cli_tools == api_tools == daemon_tools
    assert "discord.send_message" in cli_tools
    assert "channel.send_text" in cli_tools


def test_tool_pipeline_policy_filter_applies_in_menu() -> None:
    tm = ToolManager()
    tm.register("demo.echo", lambda params: {"status": "ok"})
    tm.set_environment_policy("prod", ToolPolicy(deny=["shell.*", "demo.*"]))

    summaries = tm.get_tool_summaries(
        max_words=8,
        context_metadata={"session_id": "s1", "domain": "core", "environment": "prod"},
    )
    assert "demo.echo" not in summaries


def test_tool_pipeline_cancellation_wrapper_blocks_execution() -> None:
    tm = ToolManager()
    tm.register("demo.long", lambda params: {"status": "ok"})
    token = CancellationToken()
    token.cancel("cancelled_by_test")
    ctx = ToolCallContext(
        metadata={"session_id": "s1", "domain": "core", "environment": "sandbox"},
        cancel_token=token,
    )
    with pytest.raises(CancelledError):
        asyncio.run(tm.call_tool(ToolCallRequest(tool_name="demo.long", payload={}), ctx=ctx))
