from __future__ import annotations
import socket
import logging
import httpx
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)

def net_inspect_port(params: Dict[str, Any], context: Any = None) -> Dict[str, Any]:
    """
    P5: Ported from OpenClaw's net-tools.
    Checks if a local port is open and attempts a health check.
    """
    port = params.get("port")
    host = params.get("host", "127.0.0.1")
    
    if not port:
        return {"status": "error", "error": "Missing port parameter."}
        
    # 1. TCP Connection Test
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(2.0)
    result = sock.connect_ex((host, int(port)))
    sock.close()
    
    is_open = (result == 0)
    
    out = {
        "status": "ok",
        "port": port,
        "is_open": is_open,
        "result": f"Port {port} is {'OPEN' if is_open else 'CLOSED'}"
    }
    
    # 2. HTTP Health Check (OpenClaw Parity)
    if is_open:
        try:
            url = f"http://{host}:{port}"
            resp = httpx.get(url, timeout=3.0)
            out["http_status"] = resp.status_code
            out["http_preview"] = resp.text[:200]
            out["result"] += f" (HTTP {resp.status_code} detected)"
        except Exception:
            pass
            
    return out
