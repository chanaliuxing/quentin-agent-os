from __future__ import annotations

import psutil
import platform
import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)

class OSAnalyzer:
    """
    Atomic-level System Vitals.
    Provides the brain with 'spatial sense' of its physical host.
    Aligned with OpenClaw's os-summary.ts.
    """
    
    @staticmethod
    def get_summary() -> Dict[str, Any]:
        """Captures hardware and resource limits."""
        return {
            "os": f"{platform.system()} {platform.release()}",
            "arch": platform.machine(),
            "cpu": {
                "count": psutil.cpu_count(logical=True),
                "usage_percent": psutil.cpu_percent(interval=None)
            },
            "memory": {
                "total_gb": round(psutil.virtual_memory().total / (1024**3), 2),
                "available_gb": round(psutil.virtual_memory().available / (1024**3), 2),
                "percent": psutil.virtual_memory().percent
            },
            "disk": {
                "free_gb": round(psutil.disk_usage('.').free / (1024**3), 2),
                "total_gb": round(psutil.disk_usage('.').total / (1024**3), 2)
            }
        }

# Global instance
os_analyzer = OSAnalyzer()
