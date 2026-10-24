from __future__ import annotations
import base64
import logging
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

try:
    import cv2
    import numpy as np
    CV2_AVAILABLE = True
except ImportError:
    CV2_AVAILABLE = False
    cv2 = None
    np = None

class ImageDiff:
    """
    P5: Ported from OpenClaw's 'Visual Delta' highlighting.
    Highlights changes between two screenshots using pixel-wise comparison.
    """
    
    @staticmethod
    def highlight_changes(
        current_b64: str, 
        previous_b64: str,
        highlight_color: Tuple[int, int, int] = (255, 0, 255), # Magenta
        alpha: float = 0.4
    ) -> Optional[str]:
        """
        Calculates pixel difference and overlays a heatmap on the current image.
        """
        if not CV2_AVAILABLE:
            return None

        try:
            # 1. Decode both images
            def decode(b64):
                nparray = np.frombuffer(base64.b64decode(b64), np.uint8)
                return cv2.imdecode(nparray, cv2.IMREAD_COLOR)
            
            img1 = decode(previous_b64)
            img2 = decode(current_b64)
            
            if img1 is None or img2 is None: return None
            if img1.shape != img2.shape:
                img1 = cv2.resize(img1, (img2.shape[1], img2.shape[0]))

            # 2. Pixel-wise Absolute Difference
            diff = cv2.absdiff(img1, img2)
            gray_diff = cv2.cvtColor(diff, cv2.COLOR_BGR2GRAY)
            
            # 3. Thresholding & Noise Reduction (OpenClaw Parity)
            _, thresh = cv2.threshold(gray_diff, 25, 255, cv2.THRESH_BINARY)
            
            # Dilate to make small changes visible to LLM
            kernel = np.ones((5, 5), np.uint8)
            dilated = cv2.dilate(thresh, kernel, iterations=2)
            
            # 4. Create Heatmap Overlay
            overlay = img2.copy()
            overlay[dilated > 0] = highlight_color
            
            # 5. Alpha Blend
            fused = cv2.addWeighted(overlay, alpha, img2, 1 - alpha, 0)
            
            # 6. Re-encode
            _, buffer = cv2.imencode('.jpg', fused, [cv2.IMWRITE_JPEG_QUALITY, 80])
            return base64.b64encode(buffer).decode('utf-8')
            
        except Exception as e:
            logger.error(f"ImageDiff: Failed to highlight changes: {e}")
            return None
