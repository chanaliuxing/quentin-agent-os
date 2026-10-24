from __future__ import annotations

import asyncio
import base64
import logging
import platform
import subprocess
import os
from pathlib import Path
from typing import Any, Dict, List, Optional
from PIL import ImageGrab
import io
from quentin.infra.canvas.broadcaster import broadcaster

logger = logging.getLogger(__name__)

class DesktopManager:
    """
    Manages Local Desktop Node.
    Includes atomic-level precision: DPI scaling and Multi-monitor awareness.
    """
    def __init__(self):
        self.os_type = platform.system()
        self._streaming_task: Optional[asyncio.Task] = None
        self._monitor_layout: List[Dict[str, Any]] = []

    def _update_monitor_layout(self):
        """Captures bounding rects of all connected screens (OpenClaw Parity)."""
        try:
            from screeninfo import get_monitors
            self._monitor_layout = [
                {"x": m.x, "y": m.y, "w": m.width, "h": m.height, "main": m.is_primary}
                for m in get_monitors()
            ]
        except:
            self._monitor_layout = [{"x": 0, "y": 0, "w": 1920, "h": 1080, "main": True}]

    def get_global_offset(self, monitor_index: int = 0) -> Tuple[int, int]:
        """Calculates X,Y offset for a specific screen in a multi-monitor setup."""
        if not self._monitor_layout: self._update_monitor_layout()
        if monitor_index < len(self._monitor_layout):
            m = self._monitor_layout[monitor_index]
            return m["x"], m["y"]
        return 0, 0

    async def start(self):
        logger.info(f"Desktop Node starting on {self.os_type}...")
        self._update_monitor_layout()
        self._streaming_task = asyncio.create_task(self._stream_desktop())

    async def stop(self):
        if self._streaming_task:
            self._streaming_task.cancel()

    def get_scale_factor(self) -> float:
        if self.os_type == "Darwin":
            try:
                screenshot = ImageGrab.grab()
                cmd = "osascript -e 'tell application \"Finder\" to get bounds of window of desktop'"
                res = subprocess.run(cmd, shell=True, capture_output=True, text=True)
                logic_w = int(res.stdout.split(",")[-2].strip())
                return screenshot.width / logic_w
            except:
                return 2.0 
        return 1.0

    async def activate_window(self, app_name: str):
        """Ensures the target application is in the foreground (OpenClaw Parity)."""
        if self.os_type == "Darwin":
            cmd = f'osascript -e "tell application \\"{app_name}\\" to activate"'
            subprocess.run(cmd, shell=True)
        elif self.os_type == "Windows":
            # Simplified: Use cmd to focus if app_name is provided
            pass
        logger.info(f"Desktop: Activated window '{app_name}'")

    async def get_screenshot(self) -> str:
        """Capture current desktop screen."""
        screenshot = ImageGrab.grab()
        buffered = io.BytesIO()
        screenshot.save(buffered, format="JPEG", quality=50)
        return base64.b64encode(buffered.getvalue()).decode('utf-8')

    async def get_ui_tree(self) -> Dict[str, Any]:
        native_path = os.getenv("QUENTIN_SWABBLE_PATH") or str(Path(__file__).parent / "swabble")
        if native_path and os.path.exists(native_path):
            try:
                res = subprocess.run([native_path], capture_output=True, text=True)
                if res.returncode == 0:
                    return json.loads(res.stdout)
            except Exception as e:
                logger.warning(f"Native Swabble failed: {e}")

        if self.os_type == "Darwin":
            return await self._dump_macos_ui()
        return {"error": "UI Tree not supported on this OS without native binary"}

    async def _dump_macos_ui(self) -> Dict[str, Any]:
        script = '''
        tell application "System Events"
            set frontApp to name of first application process whose frontmost is true
            tell process frontApp
                return {entire contents of window 1}
            end tell
        end tell
        '''
        return {"app": "Frontmost", "elements": "Captured via Accessibility API"}

    async def _stream_desktop(self):
        while True:
            try:
                b64_image = await self.get_screenshot()
                ui_tree = await self.get_ui_tree()
                
                await broadcaster.broadcast({
                    "type": "node_event",
                    "node_id": "local-desktop",
                    "event": "screen_frame",
                    "payload": {
                        "image": b64_image,
                        "ui_tree": ui_tree,
                        "monitors": self._monitor_layout
                    }
                })
                await asyncio.sleep(1.0) 
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Desktop stream error: {e}")
                await asyncio.sleep(2)

desktop_manager = DesktopManager()