from __future__ import annotations
import logging
from typing import Dict, Any, List, Optional
from quentin.infra.canvas.ui_protocol import UIProtocol
from quentin.infra.canvas.broadcaster import broadcaster

logger = logging.getLogger(__name__)

async def ui_render_component(params: Dict[str, Any], context: Any = None) -> Dict[str, Any]:
    """
    P5: Ported from OpenClaw's Canvas tools.
    Renders an interactive UI component on the user's dashboard.
    """
    comp_type = params.get("type", "ActionCard")
    props = params.get("props", {})
    
    # 1. Build Protocol Payload
    if comp_type == "DiffViewer":
        payload = UIProtocol.create_diff_view(props.get("path", ""), props.get("diff", ""))
    elif comp_type == "ActionCard":
        payload = UIProtocol.create_action_card(props.get("title", "Action Required"), props.get("actions", ["OK"]))
    elif comp_type == "DataTable":
        payload = UIProtocol.create_data_table(props.get("headers", []), props.get("rows", []))
    else:
        return {"status": "error", "error": f"Unsupported component type: {comp_type}"}

    # 2. Physical Broadcast (A2UI Protocol)
    await broadcaster.broadcast_component(payload)
    
    return {
        "status": "ok",
        "component_id": payload["component_id"],
        "result": f"Component {comp_type} rendered successfully."
    }
