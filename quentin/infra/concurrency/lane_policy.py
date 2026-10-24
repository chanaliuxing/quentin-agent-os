from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, Any, Optional

@dataclass
class LaneQuota:
    max_concurrency: int = 5
    current_concurrency: int = 0

class LanePolicy:
    """
    P4-B: Lane Policy & Quota
    Manages quotas and policies for lanes across different tenants and sessions.
    """
    def __init__(self) -> None:
        self.tenant_quotas: Dict[str, LaneQuota] = {}
        self.global_circuit_breaker_threshold: int = 100
        self.current_global_concurrency: int = 0

    def get_tenant_quota(self, tenant_id: str) -> LaneQuota:
        if tenant_id not in self.tenant_quotas:
            # Default quota if not specified
            self.tenant_quotas[tenant_id] = LaneQuota(max_concurrency=5)
        return self.tenant_quotas[tenant_id]

    def acquire_slot(self, tenant_id: str) -> bool:
        """
        Attempt to acquire a concurrency slot for a tenant.
        Returns True if successful, False if quota exceeded or circuit breaker tripped.
        """
        if self.current_global_concurrency >= self.global_circuit_breaker_threshold:
            return False
        
        quota = self.get_tenant_quota(tenant_id)
        if quota.current_concurrency < quota.max_concurrency:
            quota.current_concurrency += 1
            self.current_global_concurrency += 1
            return True
        return False

    def release_slot(self, tenant_id: str) -> None:
        """
        Release a concurrency slot for a tenant.
        """
        if tenant_id in self.tenant_quotas:
            self.tenant_quotas[tenant_id].current_concurrency = max(0, self.tenant_quotas[tenant_id].current_concurrency - 1)
            self.current_global_concurrency = max(0, self.current_global_concurrency - 1)

    def update_quota(self, tenant_id: str, max_concurrency: int) -> None:
        quota = self.get_tenant_quota(tenant_id)
        quota.max_concurrency = max_concurrency
