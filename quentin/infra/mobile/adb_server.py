from __future__ import annotations

import logging
import asyncio
from typing import Dict, Any
from fastapi import FastAPI
from .adb_client import ADBClient
import uvicorn

logger = logging.getLogger(__name__)

class RemoteADBProxy:
    """
    Exposes a local ADB-connected device as a network service.
    Aligned with OpenClaw's src/node-host logic.
    """
    def __init__(self, device_id: str = None):
        self.client = ADBClient(device_id)
        self.app = FastAPI(title=f"Quentin Remote ADB [{device_id or 'default'}]")
        self._setup_routes()

    def _setup_routes(self):
        @self.app.get("/screenshot")
        async def get_screenshot():
            return {"image": self.client.get_screenshot()}

        @self.app.post("/tap")
        async def tap(x: int, y: int):
            self.client.tap(x, y)
            return {"status": "ok"}

        @self.app.post("/text")
        async def type_text(text: str):
            self.client.type_text(text)
            return {"status": "ok"}

    def start(self, host: str = "0.0.0.0", port: int = 9001):
        logger.info(f"ADB Remote Proxy started on {host}:{port}")
        uvicorn.run(self.app, host=host, port=port)

# This can be launched on any machine with physical USB connections
