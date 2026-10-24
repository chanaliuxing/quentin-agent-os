from __future__ import annotations

import logging
from typing import List, Dict, Any, Tuple
from quentin.llm.client import call_llm

logger = logging.getLogger(__name__)

class HybridVisionAnalyzer:
    """
    Supplements UI Tree with Visual OCR.
    Used when UI Tree is empty (Games, Flutter, WebViews).
    """
    
    @staticmethod
    async def get_visual_nodes(b64_image: str) -> List[Dict[str, Any]]:
        """
        Calls a Vision LLM to identify all text and icons on the screen.
        Returns a 'synthetic' UI tree.
        """
        prompt = (
            "Analyze this mobile screen. List every interactable text and icon.\n"
            "Return JSON: [{\"name\": \"Login\", \"role\": \"button\", \"bounds\": [x, y, w, h]}, ...]"
        )
        
        try:
            # We use a fast VL model for OCR
            res_json = call_llm(
                config="gemini-1.5-flash",
                user_prompt=prompt,
                images=[b64_image],
                actor="hybrid_vision"
            )
            # parse res_json
            import json
            return json.loads(res_json)
        except Exception as e:
            logger.error(f"Hybrid Vision failed: {e}")
            return []

# Global instance
vision_analyzer = HybridVisionAnalyzer()
