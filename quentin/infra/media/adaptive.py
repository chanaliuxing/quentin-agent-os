from __future__ import annotations

import logging
import io
from PIL import Image
from typing import Tuple

logger = logging.getLogger(__name__)

class AdaptiveMediaGuard:
    """
    Model-specific Image Optimization.
    Aligned with OpenClaw's media-limits.ts.
    """
    
    @staticmethod
    def optimize_for_model(img_bytes: bytes, model_id: str) -> bytes:
        """
        Resizes and compresses image based on model-specific sweet spots.
        """
        img = Image.open(io.BytesIO(img_bytes))
        width, height = img.size
        
        # 1. Define Model Limits (Atomic Details)
        # GPT-4o: Max 2048px on long side for high-res mode
        # Gemini: Max 3072px
        # Claude: Max 8000px but recommended < 1568px
        
        target_max_side = 1568 # Default safe bet
        if "gpt-4o" in model_id.lower():
            target_max_side = 2048
        elif "gemini" in model_id.lower():
            target_max_side = 3072
        
        # 2. Scale if needed
        if max(width, height) > target_max_side:
            scale = target_max_side / float(max(width, height))
            new_size = (int(width * scale), int(height * scale))
            img = img.resize(new_size, Image.Resampling.LANCZOS)
            logger.debug(f"AdaptiveMedia: Scaled image to {new_size} for {model_id}")

        # 3. Compress
        output = io.BytesIO()
        img.save(output, format="JPEG", quality=75, optimize=True)
        return output.getvalue()

# Global helper
media_guard = AdaptiveMediaGuard()
