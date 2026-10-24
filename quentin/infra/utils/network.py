from __future__ import annotations

import socket
import logging
from typing import Optional

logger = logging.getLogger(__name__)

class NetworkUtils:
    """
    Network utilities ported from OpenClaw's infra logic.
    """
    
    @staticmethod
    def find_free_port(start_port: int = 8888, max_attempts: int = 100) -> int:
        """
        Finds an available TCP port starting from start_port.
        """
        for port in range(start_port, start_port + max_attempts):
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                try:
                    s.bind(('0.0.0.0', port))
                    return port
                except OSError:
                    continue
        
        raise RuntimeError(f"Could not find a free port in range {start_port}-{start_port + max_attempts}")

    @staticmethod
    def is_port_in_use(port: int) -> bool:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            return s.connect_ex(('localhost', port)) == 0

# Global instance
network_utils = NetworkUtils()
