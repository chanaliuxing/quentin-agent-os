from __future__ import annotations

from pathlib import Path
from quentin.kernel.interceptors.base import (
    SecurityInterceptor,
    SecurityInterceptorRegistry,
    get_security_interceptor_registry,
)
from quentin.kernel.interceptors.path_traversal import PathTraversalInterceptor
from quentin.kernel.interceptors.destructive_command import DestructiveCommandInterceptor
from quentin.kernel.interceptors.bash_injection import BashInjectionInterceptor
from quentin.kernel.interceptors.sensitive_files import SensitiveFileAccessInterceptor

def bootstrap_interceptors(repo_root: str | Path = ".", registry: SecurityInterceptorRegistry = None) -> SecurityInterceptorRegistry:
    if registry is None:
        registry = get_security_interceptor_registry()
    
    # 1. ESSENTIAL INTERCEPTORS (Always ON, cannot be disabled via flags)
    registry.register(PathTraversalInterceptor(repo_root=repo_root))
    registry.register(SensitiveFileAccessInterceptor(repo_root=repo_root))
    
    # 2. CONFIGURABLE INTERCEPTORS (Subject to QUENTIN_POLICY_INTERCEPTORS flag)
    import os
    if os.getenv("QUENTIN_POLICY_INTERCEPTORS", "1") == "1":
        registry.register(DestructiveCommandInterceptor())
        registry.register(BashInjectionInterceptor())
    
    return registry

__all__ = [
    "SecurityInterceptor",
    "SecurityInterceptorRegistry",
    "get_security_interceptor_registry",
    "bootstrap_interceptors",
]
