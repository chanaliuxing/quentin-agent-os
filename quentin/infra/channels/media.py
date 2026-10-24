from __future__ import annotations

import base64
import logging
import os
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

class MediaProcessor:
    """
    Handles downloading and converting channel attachments.
    Aligned with OpenClaw's MediaUnderstanding logic.
    """
    def __init__(self, download_dir: str = "data/media/inbound"):
        self.download_dir = Path(download_dir)
        self.download_dir.mkdir(parents=True, exist_ok=True)

    def to_base64(self, file_path: str | Path) -> str:
        """Converts a local file to Base64 string for Vision LLM."""
        path = Path(file_path)
        if not path.exists():
            return ""
        with open(path, "rb") as image_file:
            return base64.b64encode(image_file.read()).decode('utf-8')

    async def save_buffer(self, buffer: bytes, extension: str = "jpg") -> str:
        """Saves a raw bytes buffer to a temporary file."""
        import uuid
        filename = f"{uuid.uuid4()}.{extension}"
        path = self.download_dir / filename
        path.write_bytes(buffer)
        return str(path)

# Global instance
media_processor = MediaProcessor()
