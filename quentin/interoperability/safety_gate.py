from __future__ import annotations
from typing import Dict, Any

class InteropSafetyGate:
    """
    P12-B: Interoperability Safety Gate
    Ensures external inputs meet local safety standards.
    """
    def sanitize_external_input(self, data: Dict[str, Any]) -> Dict[str, Any]:
        # Redact sensitive fields from external sources before internal processing
        sanitized = data.copy()
        forbidden_keys = {"api_key", "password", "token"}
        for k in forbidden_keys:
            if k in sanitized:
                sanitized[k] = "[REDACTED_BY_INTEROP_GATE]"
        return sanitized
