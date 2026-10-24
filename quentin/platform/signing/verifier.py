from __future__ import annotations
import hashlib
import hmac
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

class PluginSignatureVerifier:
    """
    P6-B: Plugin Signature Verifier
    Ensures supply-chain security for external extensions.
    """
    def __init__(self, trust_keys: Dict[str, str]) -> None:
        self.trust_keys = trust_keys # publisher_id -> public_key/secret

    def verify_manifest(self, manifest_data: Dict[str, Any], signature: str, publisher_id: str) -> bool:
        """
        Verify the signature of a manifest.
        """
        secret = self.trust_keys.get(publisher_id)
        if not secret:
            logger.warning("Publisher '%s' is not in the trust list.", publisher_id)
            return False

        # In a real system, use RSA/Ed25519. Here we use HMAC for demo purposes.
        payload = hashlib.sha256(str(manifest_data).encode()).hexdigest()
        expected_sig = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()
        
        return hmac.compare_digest(expected_sig, signature)
