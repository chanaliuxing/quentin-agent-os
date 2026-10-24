from __future__ import annotations
import logging
import asyncio
from typing import Dict, Any, List
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect

from quentin.infra.channels.provider import ChannelProvider
from quentin.infra.channels.contracts import GatewayInboundMessage as InboundMessage, GatewayOutboundMessage as OutboundMessage
from quentin.config.feature_flags import feature_flags

logger = logging.getLogger(__name__)

class GatewayServer:
    """
    Tier 0 Gateway Server.
    Provides HTTP/WS endpoints for channel interaction.
    """
    def __init__(self):
        self.app = FastAPI(title="Quentin Gateway")
        self._providers: Dict[str, ChannelProvider] = {}
        self._active_connections: List[WebSocket] = []
        self._setup_routes()

    def register_provider(self, provider: ChannelProvider):
        self._providers[provider.provider_id] = provider
        logger.info(f"Gateway: Registered provider {provider.provider_id}")

    def _setup_routes(self):
        @self.app.post("/gateway/messages/inbound")
        async def inbound(msg: InboundMessage):
            if not feature_flags.gateway_v1:
                raise HTTPException(status_code=503, detail="Gateway V1 disabled")
            
            # Forward to internal logic (Lane Orchestrator)
            from quentin.infra.concurrency.lane_orchestrator import lane_orchestrator
            
            session_id = msg.session_id or f"{msg.channel}:{msg.chat_id}"
            tenant_id = str(getattr(msg, "tenant_id", "default") or "default")
            lane_key = f"session:{session_id}"
            
            logger.info(f"Gateway: Inbound from {msg.sender_id} in {lane_key}")
            
            # P2: Actual Wiring
            try:
                from quentin.bootstrap.container import Container
                from quentin.cognitive.loop import CognitiveTask
                
                brain = Container().cognitive_loop
                task = CognitiveTask(
                    input_text=msg.text,
                    metadata={
                        "session_id": session_id,
                        "tenant_id": tenant_id,
                        "sender": msg.sender_id,
                        "source": f"gateway:{msg.channel}",
                    }
                )
                
                # Execute asynchronously
                # We use lane_orchestrator implicitly inside run_task_async, but we want to fire-and-forget here
                # so the HTTP request returns immediately.
                asyncio.create_task(brain.run_task_async(task))
                
            except Exception as e:
                logger.error(f"Gateway execution failed: {e}")
                # We still return accepted, as it's async processing
            
            return {"status": "accepted", "lane": lane_key}

        @self.app.post("/gateway/messages/outbound")
        async def outbound(msg: OutboundMessage):
            if not feature_flags.gateway_v1:
                raise HTTPException(status_code=503, detail="Gateway V1 disabled")
                
            provider = self._providers.get(msg.channel)
            if not provider:
                raise HTTPException(status_code=404, detail=f"Provider {msg.channel} not found")
            
            await provider.send_text(msg.target_id, msg.text)
            return {"status": "sent"}

        @self.app.websocket("/gateway/events")
        async def websocket_endpoint(websocket: WebSocket):
            if not feature_flags.gateway_v1:
                await websocket.close(code=1003)
                return
                
            await websocket.accept()
            self._active_connections.append(websocket)
            try:
                while True:
                    # Echo for now, or stream logs
                    data = await websocket.receive_text()
                    await websocket.send_text(f"Echo: {data}")
            except WebSocketDisconnect:
                self._active_connections.remove(websocket)

gateway = GatewayServer()
