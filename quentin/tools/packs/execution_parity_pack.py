from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from quentin.tools.execution_parity import (
    agent_step_tool,
    agents_list_tool,
    canvas_tool,
    channels_listener_tool_async,
    cron_tool,
    discord_actions,
    gateway_tool,
    image_tool,
    message_tool,
    memory_get_tool,
    memory_search_tool,
    nodes_tool,
    session_status_tool,
    sessions_announce_target,
    sessions_history_tool,
    sessions_list_tool,
    sessions_send_tool,
    sessions_spawn_tool,
    slack_actions,
    telegram_actions,
    tool_specs,
    tts_tool,
    web_fetch_tool,
    web_search_tool,
    web_readability_tool,
    whatsapp_actions,
)
from quentin.tools.schemas import ToolKind, ToolSpec


@dataclass(frozen=True)
class ExecutionParityToolPack:
    id: str = "execution_parity"
    priority: int = 35

    def enabled(self, *, container: Any) -> bool:
        return True

    def register(self, *, tool_manager: Any, repo_root: Any, container: Any) -> None:
        handlers = {
            "agent.step": agent_step_tool,
            "gateway.tool": gateway_tool,
            "message.tool": message_tool,
            "discord.actions": discord_actions,
            "slack.actions": slack_actions,
            "telegram.actions": telegram_actions,
            "whatsapp.actions": whatsapp_actions,
            "channels.listener": channels_listener_tool_async,
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
        for name, desc, domain, meta in tool_specs():
            spec = ToolSpec(
                name=name,
                description=desc,
                kind=ToolKind.external if domain in {"communication", "web"} else ToolKind.builtin,
                domain=domain,
                meta=dict(meta or {}),
            )
            tool_manager.register_tool(spec, handlers[name])
