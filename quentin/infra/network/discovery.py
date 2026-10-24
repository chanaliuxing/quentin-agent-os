from __future__ import annotations

import socket
import logging
import time
from typing import List, Dict, Any
try:
    from zeroconf import IPVersion, ServiceInfo, Zeroconf
except ImportError:
    Zeroconf = None # Optional dependency

logger = logging.getLogger(__name__)

class NetworkDiscovery:
    """
    mDNS/Bonjour Service Discovery.
    Allows nodes to find each other without manual IP entry.
    Aligned with OpenClaw's infra/bonjour.ts.
    """
    def __init__(self, service_name: str = "QuentinBrain"):
        self.service_name = service_name
        self.zc = Zeroconf() if Zeroconf else None
        self._advertised_port: int = 0
        self._last_advertised_ts: float = 0.0
        self._active: bool = False

    def advertise_service(self, port: int):
        """Broadcasts this service to the local network."""
        if not self.zc:
            logger.warning("NetworkDiscovery: zeroconf not installed. Skipping broadcast.")
            return

        desc = {'version': '1.0', 'os': 'quentin-os'}
        info = ServiceInfo(
            "_quentin._tcp.local.",
            f"{self.service_name}._quentin._tcp.local.",
            addresses=[socket.inet_aton("127.0.0.1")], # Simplified
            port=port,
            properties=desc,
            server=f"{socket.gethostname()}.local."
        )
        self.zc.register_service(info)
        self._advertised_port = int(port)
        self._last_advertised_ts = float(time.time())
        self._active = True
        logger.info(f"NetworkDiscovery: Advertising {self.service_name} on port {port}")

    def stop(self):
        if self.zc:
            self.zc.unregister_all_services()
            self.zc.close()
        self._active = False

    def get_status(self) -> Dict[str, Any]:
        return {
            "service_name": self.service_name,
            "active": bool(self._active),
            "port": int(self._advertised_port or 0),
            "last_advertised_ts": float(self._last_advertised_ts or 0.0),
            "zeroconf_available": bool(self.zc is not None),
            "hostname": socket.gethostname(),
        }

# Global singleton
discovery = NetworkDiscovery()
