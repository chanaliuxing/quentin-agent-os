from __future__ import annotations
import base64
import logging
from typing import List, Dict, Any, Tuple, Optional

logger = logging.getLogger(__name__)

try:
    import cv2
    import numpy as np
    CV2_AVAILABLE = True
except ImportError:
    CV2_AVAILABLE = False
    cv2 = None
    np = None

class VisionUtils:
    """
    P5: Ported from OpenClaw's 'Foveated Perception'.
    Handles intelligent cropping and visual focus for multimodal agents.
    """
    
    @staticmethod
    def crop_focus_area(
        image_b64: str, 
        center_x: int, 
        center_y: int, 
        window_size: int = 512
    ) -> str:
        """
        Crops a high-res window around a specific coordinate.
        """
        if not CV2_AVAILABLE:
            return image_b64 # Fallback to full image

        try:
            # 1. Decode
            nparray = np.frombuffer(base64.b64decode(image_b64), np.uint8)
            img = cv2.imdecode(nparray, cv2.IMREAD_COLOR)
            h, w, _ = img.shape
            
            # 2. Calculate Bounds with Edge Padding (OpenClaw Parity)
            half = window_size // 2
            
            x1 = max(0, center_x - half)
            y1 = max(0, center_y - half)
            x2 = min(w, x1 + window_size)
            y2 = min(h, y1 + window_size)
            
            # Recalibrate x1, y1 if near right/bottom edges
            if x2 == w: x1 = max(0, w - window_size)
            if y2 == h: y1 = max(0, h - window_size)
            
            # 3. Physical Crop
            cropped = img[y1:y2, x1:x2]
            
            # 4. Re-encode
            _, buffer = cv2.imencode('.jpg', cropped, [cv2.IMWRITE_JPEG_QUALITY, 90])
            return base64.b64encode(buffer).decode('utf-8')
        except Exception as e:
            logger.error(f"VisionUtils: Crop failed: {e}")
            return image_b64

    @staticmethod
    def get_element_center(bounds: List[float]) -> Tuple[int, int]:
        """[x, y, w, h] -> (cx, cy)"""
        x, y, w, h = bounds
        return int(x + w / 2), int(y + h / 2)
