from __future__ import annotations

import subprocess
import logging
import json
from typing import Dict, Optional

logger = logging.getLogger(__name__)

class TailscaleBridge:
    """
    Manages Tailscale secure networking status.
    Ported from OpenClaw's infra/tailnet.ts.
    """
    
    @staticmethod
    def get_status() -> Dict[str, Any]:
        """Runs `tailscale status --json`."""
        try:
            res = subprocess.run(["tailscale", "status", "--json"], capture_output=True, text=True)
            if res.returncode == 0:
                return json.loads(res.stdout)
        except FileNotFoundError:
            return {"error": "Tailscale binary not found"}
        except Exception as e:
            logger.error(f"Tailscale status check failed: {e}")
        return {}

    @staticmethod
    def get_self_ip() -> Optional[str]:
        """Gets the Tailnet IP of this machine."""
        status = TailscaleBridge.get_status()
        if "Self" in status:
            ips = status["Self"].get("TailscaleIPs", [])
            if ips:
                return ips[0]
        return None

# Global instance
tailscale_bridge = TailscaleBridge()
