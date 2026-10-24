from __future__ import annotations

import asyncio
import json
import logging
import uuid
from typing import Dict, Any, Optional, Set
try:
    import websockets
    WEBSOCKETS_AVAILABLE = True
except ImportError:
    WEBSOCKETS_AVAILABLE = False
    websockets = Any  # type: ignore
from .types import ACPMethod, ACPRequest, ACPResponse

logger = logging.getLogger(__name__)

class ACPServer:
    """
    Quentin ACP Gateway.
    Handles long-running WebSocket connections from mobile nodes (Android/iOS).
    """
    def __init__(self, host: str = "0.0.0.0", port: int = 8888):
        self.host = host
        self.port = port
        # node_id -> websocket
        self._connected_nodes: Dict[str, websockets.WebSocketServerProtocol] = {}
        self._node_capabilities: Dict[str, List[str]] = {}
        self._pending_requests: Dict[str, asyncio.Future] = {}
        self._heartbeat_task: Optional[asyncio.Task] = None

    async def start(self):
        self._heartbeat_task = asyncio.create_task(self._run_heartbeat())
        async with websockets.serve(self._handle_connection, self.host, self.port):
            logger.info(f"ACP Server started on {self.host}:{self.port}")
            await asyncio.Future()

    async def _run_heartbeat(self):
        """Application level heartbeat to keep connections alive."""
        while True:
            await asyncio.sleep(30)
            async with asyncio.Lock():
                nodes = list(self._connected_nodes.items())
            
            for node_id, ws in nodes:
                try:
                    await ws.send(json.dumps({
                        "jsonrpc": "2.0",
                        "method": ACPMethod.SERVER_HEARTBEAT,
                        "params": {"timestamp": time.time()}
                    }))
                except Exception:
                    logger.warning(f"Heartbeat failed for {node_id}, closing...")
                    await ws.close()

    async def _handle_connection(self, websocket: websockets.WebSocketServerProtocol, path: str):
        node_id = None
        try:
            async for message in websocket:
                data = json.loads(message)
                
                # Handle Response
                if "id" in data and ("result" in data or "error" in data):
                    req_id = data["id"]
                    if req_id in self._pending_requests:
                        self._pending_requests[req_id].set_result(data)
                    continue

                # Handle Inbound Method Calls
                method = data.get("method")
                params = data.get("params", {})

                if method == ACPMethod.NODE_REGISTER:
                    node_id = params.get("node_id", str(uuid.uuid4()))
                    self._connected_nodes[node_id] = websocket
                    self._node_capabilities[node_id] = params.get("capabilities", [])
                    logger.info(f"Node Registered: {node_id} with capabilities: {self._node_capabilities[node_id]}")
                    await websocket.send(json.dumps({"jsonrpc": "2.0", "id": data.get("id"), "result": "ok"}))

                elif method == ACPMethod.NODE_EVENT:
                    event_type = params.get("event_type")
                    from quentin.infra.canvas.broadcaster import broadcaster
                    
                    # Forward everything from node to web dashboards
                    await broadcaster.broadcast({
                        "type": "node_event",
                        "node_id": node_id,
                        "event": event_type,
                        "payload": params
                    })

                    if event_type == "screen_frame":
                        pass
                    elif event_type == "log":
                        logger.info(f"Node Log [{node_id}]: {params.get('message')}")

        except Exception as e:
            logger.error(f"ACP Connection error: {e}")
        finally:
            if node_id and node_id in self._connected_nodes:
                del self._connected_nodes[node_id]
                logger.info(f"Node Disconnected: {node_id}")

    async def invoke_mobile_tool(self, node_id: str, tool_name: str, args: Dict[str, Any]) -> Any:
        """
        Invoke a tool on the mobile device.
        """
        if node_id not in self._connected_nodes:
            raise RuntimeError(f"Mobile node {node_id} is not connected.")

        ws = self._connected_nodes[node_id]
        req_id = str(uuid.uuid4())
        request = ACPRequest(id=req_id, method=ACPMethod.NODE_INVOKE, params={
            "tool_name": tool_name,
            "args": args
        })

        future = asyncio.get_event_loop().create_future()
        self._pending_requests[req_id] = future

        try:
            await ws.send(json.dumps(request.to_dict()))
            # Wait for response with timeout
            response_raw = await asyncio.wait_for(future, timeout=30.0)
            response = ACPResponse.from_dict(response_raw)
            if response.error:
                raise RuntimeError(f"Mobile tool error: {response.error}")
            return response.result
        finally:
            del self._pending_requests[req_id]

# Global instance for easy access
gateway = ACPServer()
