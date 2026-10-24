from __future__ import annotations

from typing import Any, Dict
from pydantic import BaseModel, Field


class GatewayInboundMessage(BaseModel):
    channel: str
    sender_id: str
    chat_id: str
    text: str
    session_id: str | None = None
    tenant_id: str | None = "default"
    metadata: Dict[str, Any] = Field(default_factory=dict)


class GatewayOutboundMessage(BaseModel):
    channel: str
    target_id: str
    text: str
    tenant_id: str | None = "default"
    metadata: Dict[str, Any] = Field(default_factory=dict)


class GatewayContractVersion(BaseModel):
    version: str = "v1"
    compatible_channels: list[str] = Field(default_factory=lambda: ["discord", "slack", "telegram", "webhook"])
    transport_modes: list[str] = Field(default_factory=lambda: ["http", "ws", "sse"])
