from __future__ import annotations

import random
import math
import asyncio
from typing import List, Tuple

class PhysicsSim:
    """
    Simulates human-like non-linear movements.
    Matches OpenClaw's internal Bezier-based trajectory logic.
    """
    
    @staticmethod
    def get_bezier_path(start: Tuple[float, float], end: Tuple[float, float], steps: int = 10) -> List[Tuple[float, float]]:
        """
        Generates a non-linear path with Ease-In/Ease-Out.
        Adds random jitter to mimic muscle micro-vibrations.
        """
        x1, y1 = start
        x2, y2 = end
        
        # Random control point for the curve
        cx = (x1 + x2) / 2 + random.uniform(-0.05, 0.05)
        cy = (y1 + y2) / 2 + random.uniform(-0.05, 0.05)
        
        path = []
        for i in range(steps + 1):
            t = i / steps
            # Quadratic Bezier formula
            curr_x = (1-t)**2 * x1 + 2*(1-t)*t * cx + t**2 * x2
            curr_y = (1-t)**2 * y1 + 2*(1-t)*t * cy + t**2 * y2
            
            # Add micro-jitter (Atomic detail)
            curr_x += random.uniform(-0.001, 0.001)
            curr_y += random.uniform(-0.001, 0.001)
            
            path.append((curr_x, curr_y))
        return path

# Global instance
sim = PhysicsSim()
