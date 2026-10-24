from __future__ import annotations
from typing import Dict, Any, List

class SyncFilter:
    """
    P7-B: Federation Sync Filter
    Filters data before synchronization to prevent leakage.
    """
    def __init__(self) -> None:
        self.allowed_keys = {"model_name", "avg_latency", "success_rate", "policy_version"}
        self.blocked_keys = {"api_key", "secret", "internal_ip", "user_pii"}

    def filter_payload(self, data: Dict[str, Any]) -> Dict[str, Any]:
        filtered = {}
        for k, v in data.items():
            if k in self.blocked_keys:
                continue
            # Basic allow-list or heuristic check
            if k in self.allowed_keys or not self._is_sensitive(k):
                filtered[k] = v
        return filtered

    def _is_sensitive(self, key: str) -> bool:
        return "key" in key.lower() or "secret" in key.lower() or "token" in key.lower()
