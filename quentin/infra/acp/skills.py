from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional
from .server import gateway

class MobileSkillBridge:
    """
    Exposes mobile node capabilities as standard Quentin Skills.
    """
    
    @staticmethod
    async def get_location(node_id: str) -> Dict[str, float]:
        """Get the current GPS coordinates of the mobile node."""
        return await gateway.invoke_mobile_tool(node_id, "location.get", {})

    @staticmethod
    async def take_photo(node_id: str, camera: str = "back") -> str:
        """Take a photo and return the image data or path."""
        return await gateway.invoke_mobile_tool(node_id, "camera.take_photo", {"camera": camera})

    @staticmethod
    async def push_notification(node_id: str, title: str, body: str):
        """Send a push notification to the phone."""
        return await gateway.invoke_mobile_tool(node_id, "ui.notify", {"title": title, "body": body})

    @staticmethod
    async def run_bash(node_id: str, command: str) -> str:
        """Run a shell command on the mobile node (e.g. via Termux)."""
        return await gateway.invoke_mobile_tool(node_id, "shell.execute", {"command": command})

    # --- A2UI (Agent-to-UI) Extensions ---

    @staticmethod
    async def get_screenshot(node_id: str) -> str:
        """Get a base64 encoded screenshot of the current screen."""
        return await gateway.invoke_mobile_tool(node_id, "ui.screenshot", {})

    @staticmethod
    async def click(node_id: str, x: int, y: int):
        """Perform a tap at the specified coordinates."""
        return await gateway.invoke_mobile_tool(node_id, "ui.click", {"x": x, "y": y})

    @staticmethod
    async def input_text(node_id: str, text: str):
        """Type text into the currently focused field."""
        return await gateway.invoke_mobile_tool(node_id, "ui.input", {"text": text})

    @staticmethod
    async def swipe(node_id: str, direction: str, distance: str = "medium"):
        """Swipe the screen (up, down, left, right)."""
        return await gateway.invoke_mobile_tool(node_id, "ui.swipe", {"direction": direction, "distance": distance})

    @staticmethod
    async def get_ui_tree(node_id: str) -> str:
        """Get the XML/JSON representation of the current UI hierarchy."""
        return await gateway.invoke_mobile_tool(node_id, "ui.dump_hierarchy", {})
