from __future__ import annotations

from typing import Any, Dict, List, Optional, Protocol, Tuple, runtime_checkable
from quentin.kernel.policy import ActionRequest

@runtime_checkable
class SecurityInterceptor(Protocol):
    """
    Interface for pluggable security interceptors (P3-A).
    These represent 'hard logic' safety checks that run before or alongside policy evaluation.
    """
    @property
    def id(self) -> str: ...

    @property
    def priority(self) -> int:
        """Higher priority interceptors run first."""
        ...

    def intercept(self, action: ActionRequest) -> Tuple[bool, Optional[str], Dict[str, Any]]:
        """
        Check if the action is allowed.
        Returns (allow, reason, audit_metadata).
        """
        ...


class SecurityInterceptorRegistry:
    """
    Registry for managing security interceptors.
    """
    def __init__(self) -> None:
        self._interceptors: Dict[str, SecurityInterceptor] = {}

    def register(self, interceptor: SecurityInterceptor) -> None:
        self._interceptors[interceptor.id] = interceptor

    def list_interceptors(self) -> List[SecurityInterceptor]:
        return sorted(self._interceptors.values(), key=lambda i: -i.priority)

    def run_all(self, action: ActionRequest) -> Tuple[bool, Optional[str], Dict[str, Any]]:
        """
        Run all registered interceptors. First deny wins.
        """
        combined_audit = {}
        for i in self.list_interceptors():
            allow, reason, audit = i.intercept(action)
            combined_audit[i.id] = audit
            if not allow:
                return False, f"Interceptor {i.id} denied: {reason}", combined_audit
        return True, None, combined_audit

# Global registry instance
_registry = SecurityInterceptorRegistry()

def get_security_interceptor_registry() -> SecurityInterceptorRegistry:
    return _registry
