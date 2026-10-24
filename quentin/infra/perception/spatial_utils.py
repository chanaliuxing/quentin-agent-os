from __future__ import annotations
import math
import logging
from typing import List, Dict, Any, Tuple

logger = logging.getLogger(__name__)

class SpatialUtils:
    """
    P5: Ported from OpenClaw's coordinate normalization logic.
    Converts raw pixels to a standardized 1000x1000 virtual grid.
    """
    
    @staticmethod
    def normalize_bounds(
        raw_bounds: List[float], 
        view_width: float, 
        view_height: float
    ) -> List[int]:
        """
        Maps [x, y, w, h] to [0-1000] scale with rounding.
        """
        if not raw_bounds or len(raw_bounds) != 4:
            return [0, 0, 0, 0]
            
        x, y, w, h = raw_bounds
        
        # 1. Coordinate Scaling
        nx = int((x / view_width) * 1000)
        ny = int((y / view_height) * 1000)
        nw = int((w / view_width) * 1000)
        nh = int((h / view_height) * 1000)
        
        # 2. Grid Alignment (OpenClaw Parity)
        # Snap to nearest 5 units to group elements on same visual lines
        def snap(val: int, step: int = 5) -> int:
            return round(val / step) * step
            
        return [
            max(0, min(1000, snap(nx))),
            max(0, min(1000, snap(ny))),
            max(0, min(1000, nw)),
            max(0, min(1000, nh))
        ]

    @staticmethod
    def get_layout_hint(normalized_bounds: List[int]) -> str:
        """
        Provides a human-readable orientation hint.
        """
        x, y, _, _ = normalized_bounds
        
        v_pos = "top" if y < 333 else "middle" if y < 666 else "bottom"
        h_pos = "left" if x < 333 else "center" if x < 666 else "right"
        
        if v_pos == "middle" and h_pos == "center":
            return "center"
        return f"{v_pos}-{h_pos}"
