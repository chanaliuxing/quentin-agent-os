from __future__ import annotations
import logging
from typing import Dict, Any
from quentin.infra.events.environment_bus import environment_bus

logger = logging.getLogger(__name__)

class UIBroadcaster:
    """
    P5: Ported from OpenClaw's Canvas Broadcaster.
    Emits UI rendering events to the frontend via the system event bus.
    """
    
    @staticmethod
    async def broadcast_component(component_data: Dict[str, Any]):
        """
        Sends a UI component to all active frontend clients.
        """
        logger.info(f"Canvas: Broadcasting component {component_data.get('type')}")
        
        # We wrap it in a special system event
        event_payload = {
            "type": "render_ui",
            "payload": component_data
        }
        
        # P5: Surgery Fifty - Environment Event Bus
        # Frontend gateways subscribe to 'ui_event' to push via SSE/WS
        environment_bus.emit("ui_event", event_payload)

broadcaster = UIBroadcaster()
