from __future__ import annotations
from typing import Dict, Any, Callable, Optional

class VersionRouter:
    """
    P6-D: Version Router
    Routes requests to different handlers based on the client's API version.
    """
    def __init__(self) -> None:
        self.routes: Dict[str, Dict[str, Callable]] = {} # endpoint -> {version -> handler}

    def register_version(self, endpoint: str, version: str, handler: Callable) -> None:
        if endpoint not in self.routes:
            self.routes[endpoint] = {}
        self.routes[endpoint][version] = handler

    def route(self, endpoint: str, version: str, *args, **kwargs) -> Any:
        handlers = self.routes.get(endpoint)
        if not handlers:
             raise ValueError(f"No routes found for endpoint: {endpoint}")
        
        handler = handlers.get(version)
        if not handler:
            # Fallback to latest or specific compatibility logic
            latest_version = sorted(handlers.keys())[-1]
            handler = handlers[latest_version]
            
        return handler(*args, **kwargs)
