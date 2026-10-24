from __future__ import annotations

import os
import subprocess
import logging
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

class CapabilityDiscovery:
    """
    Probes the real environment to find active 'eyes' and 'hands'.
    Aligned with OpenClaw's dynamic Node discovery.
    """
    
    @staticmethod
    def check_mobile_active() -> bool:
        """Checks if an Android device is connected via ADB."""
        try:
            res = subprocess.run(["adb", "devices"], capture_output=True, text=True)
            lines = res.stdout.strip().splitlines()
            return len(lines) > 1 # First line is 'List of devices attached'
        except:
            return False

    @staticmethod
    def check_browser_active() -> bool:
        """Checks if Playwright is installed and ready."""
        try:
            import playwright
            return True
        except ImportError:
            return False

    @staticmethod
    def check_tailscale_active() -> bool:
        """Checks if Tailscale is running."""
        try:
            res = subprocess.run(["tailscale", "status"], capture_output=True)
            return res.returncode == 0
        except:
            return False

    @classmethod
    def get_active_capabilities(cls) -> Dict[str, bool]:
        return {
            "mobile": cls.check_mobile_active(),
            "browser": cls.check_browser_active(),
            "tailscale": cls.check_tailscale_active(),
            "sandbox": os.getenv("ENABLE_EVOLVER_SANDBOX") == "1"
        }
