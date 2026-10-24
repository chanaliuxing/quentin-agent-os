from __future__ import annotations

import httpx
import logging
import asyncio
from typing import Optional

logger = logging.getLogger(__name__)

class ModelPrewarmer:
    """
    Optimizes the first-token latency by pre-loading models.
    Aligned with OpenClaw's local model pre-warming logic.
    """
    def __init__(self, base_url: str = "http://localhost:11434"):
        self.base_url = base_url.rstrip("/")

    async def prewarm(self, model_id: str):
        """
        Sends a minimal prompt to trigger model loading into VRAM.
        """
        logger.info(f"Ollama: Pre-warming model '{model_id}'...")
        payload = {
            "model": model_id,
            "prompt": "", 
            "stream": False,
            "keep_alive": "5m" # Keep in memory for 5 minutes
        }
        
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                await client.post(f"{self.base_url}/api/generate", json=payload)
                logger.info(f"Ollama: Model '{model_id}' is now warmed up and in VRAM.")
        except Exception as e:
            logger.warning(f"Ollama Pre-warm failed: {e}")

# Global instance
prewarmer = ModelPrewarmer()
