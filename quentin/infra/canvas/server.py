from __future__ import annotations

import logging
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from .broadcaster import broadcaster
from quentin.infra.acp.server import gateway
import uvicorn

logger = logging.getLogger(__name__)

app = FastAPI(title="Quentin Canvas Server")

@app.websocket("/ws/canvas")
async def canvas_socket(websocket: WebSocket):
    await websocket.accept()
    await broadcaster.register(websocket)
    try:
        while True:
            # Handle inbound commands from the Web UI (Human-in-the-loop)
            data = await websocket.receive_json()
            command = data.get("command")
            node_id = data.get("node_id")
            
            if command == "click":
                coords = data.get("coords", [0, 0])
                await gateway.invoke_mobile_tool(node_id, "ui.click", {"x": coords[0], "y": coords[1]})
            elif command == "resolve_approval":
                req_id = data.get("request_id")
                decision = data.get("decision") # bool
                from quentin.infra.security.approval import approval_gate
                approval_gate.resolve_request(req_id, decision)
                logger.info(f"Canvas: User resolved approval {req_id} as {decision}")
            elif command == "swipe":
                direction = data.get("direction")
                await gateway.invoke_mobile_tool(node_id, "ui.swipe", {"direction": direction})
            elif command == "type":
                text = data.get("text")
                await gateway.invoke_mobile_tool(node_id, "ui.input", {"text": text})
                
    except WebSocketDisconnect:
        await broadcaster.unregister(websocket)
    except Exception as e:
        logger.error(f"Canvas: Socket error: {e}")
        await broadcaster.unregister(websocket)

def start_canvas_server(host: str = "0.0.0.0", port: int = 8889):
    logger.info(f"Starting Canvas Server on {host}:{port}")
    uvicorn.run(app, host=host, port=port)
