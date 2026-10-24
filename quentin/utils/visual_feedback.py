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

class VisualFeedbackEngine:
    """
    P5: Ported from OpenClaw's 'Post-click Verification'.
    Detects if the UI actually changed after a click by comparing local pixels.
    """
    
    @staticmethod
    def capture_region(page_screenshot_b64: str, cx: int, cy: int, size: int = 64) -> Optional[np.ndarray]:
        if not CV2_AVAILABLE: return None
        try:
            nparray = np.frombuffer(base64.b64decode(page_screenshot_b64), np.uint8)
            img = cv2.imdecode(nparray, cv2.IMREAD_COLOR)
            h, w, _ = img.shape
            
            x1 = max(0, cx - size // 2)
            y1 = max(0, cy - size // 2)
            x2 = min(w, x1 + size)
            y2 = min(h, y1 + size)
            
            return img[y1:y2, x1:x2]
        except Exception:
            return None

    @staticmethod
    def has_visual_reaction(img1: np.ndarray, img2: np.ndarray, threshold: float = 0.01) -> bool:
        """
        Returns True if the difference between two images exceeds the threshold.
        """
        if img1 is None or img2 is None: return True # Default to true if comparison fails
        if img1.shape != img2.shape: return True
        
        # 1. Absolute Difference
        diff = cv2.absdiff(img1, img2)
        
        # 2. Sum of changed pixels (OpenClaw Parity)
        gray_diff = cv2.cvtColor(diff, cv2.COLOR_BGR2GRAY)
        _, thresh = cv2.threshold(gray_diff, 15, 255, cv2.THRESH_BINARY)
        
        change_rate = np.count_nonzero(thresh) / thresh.size
        logger.debug(f"VisualFeedback: Measured change rate: {change_rate:.4f}")
        
        return change_rate > threshold
