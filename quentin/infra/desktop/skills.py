from __future__ import annotations

import logging
import asyncio
try:
    import pyautogui
except ImportError:
    pyautogui = None
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

class DesktopSkills:
    """
    High-precision skills for local desktop control.
    """

    @staticmethod
    async def click(x: int, y: int):
        if not pyautogui: return "Error: pyautogui not installed"
        pyautogui.click(x, y)
        return f"Clicked at {x}, {y}"

    @staticmethod
    async def drag_and_drop(start_x: int, start_y: int, end_x: int, end_y: int):
        """
        Atomic Parity: Performs a physical drag-and-drop using non-linear Bezier movement.
        """
        if not pyautogui: return "Error: pyautogui not installed"
        from quentin.infra.utils.physics import sim
        
        pyautogui.moveTo(start_x, start_y, duration=0.2)
        pyautogui.mouseDown()
        await asyncio.sleep(0.2) 
        
        path = sim.get_bezier_path((start_x, start_y), (end_x, end_y), steps=15)
        for px, py in path:
            pyautogui.moveTo(px, py)
            
        await asyncio.sleep(0.1)
        pyautogui.mouseUp()
        return f"Dragged from ({start_x}, {start_y}) to ({end_x}, {end_y})"

    @staticmethod
    async def type_text(text: str):
        if not pyautogui: return "Error: pyautogui not installed"
        pyautogui.write(text, interval=0.05)
        return f"Typed: {text}"

    @staticmethod
    async def press_key(key: str):
        if not pyautogui: return "Error: pyautogui not installed"
        if '+' in key:
            keys = key.split('+')
            pyautogui.hotkey(*keys)
        else:
            pyautogui.press(key)
        return f"Pressed key: {key}"

    @staticmethod
    async def get_screen_info() -> Dict[str, Any]:
        if not pyautogui: return {"error": "pyautogui not installed"}
        size = pyautogui.size()
        pos = pyautogui.position()
        return {
            "screen_size": {"width": size.width, "height": size.height},
            "mouse_pos": {"x": pos.x, "y": pos.y}
        }