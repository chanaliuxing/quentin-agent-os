from __future__ import annotations
import base64
import logging
from typing import List, Dict, Any, Tuple

logger = logging.getLogger(__name__)

try:
    import cv2
    import numpy as np
    CV2_AVAILABLE = True
except ImportError:
    CV2_AVAILABLE = False
    cv2 = None
    np = None

class SoMVisualizer:
    """
    P5: Ported from OpenClaw's Set-of-Mark (SoM) visualizer.
    Labels elements on a screenshot with their ref IDs (e1, e2, ...).
    """
    @staticmethod
    def apply_marks(image_b64: str, marks: Dict[str, List[float]]) -> str:
        """
        Draws boxes and IDs on the image.
        marks: ref_id -> [x, y, w, h]
        """
        if not CV2_AVAILABLE:
            logger.warning("SoMVisualizer: OpenCV not installed. Skipping visual markup.")
            return image_b64

        try:
            # Decode image
            nparray = np.frombuffer(base64.b64decode(image_b64), np.uint8)
            img = cv2.imdecode(nparray, cv2.IMREAD_COLOR)
            
            for ref_id, bounds in marks.items():
                if not bounds or len(bounds) != 4: continue
                
                x, y, w, h = map(int, bounds)
                
                # 1. Draw semi-transparent box (Atomic Detail)
                overlay = img.copy()
                cv2.rectangle(overlay, (x, y), (x + w, y + h), (0, 0, 255), 2)
                alpha = 0.3
                cv2.addWeighted(overlay, alpha, img, 1 - alpha, 0, img)
                
                # 2. Draw Label Background
                label = ref_id
                (l_w, l_h), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
                cv2.rectangle(img, (x, y - l_h - 5), (x + l_w + 5, y), (0, 0, 255), -1)
                
                # 3. Draw ID Text
                cv2.putText(img, label, (x + 2, y - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)

            # Encode back to b64
            _, buffer = cv2.imencode('.jpg', img, [cv2.IMWRITE_JPEG_QUALITY, 80])
            return base64.b64encode(buffer).decode('utf-8')
        except Exception as e:
            logger.error(f"SoMVisualizer: Failed to apply marks: {e}")
            return image_b64
