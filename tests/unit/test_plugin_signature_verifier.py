import pytest
import hmac
import hashlib
from quentin.platform.signing.verifier import PluginSignatureVerifier

def test_signature_verification_success():
    trust_keys = {"pub_1": "secret_key"}
    verifier = PluginSignatureVerifier(trust_keys)
    
    manifest = {"name": "test_plugin", "version": "1.0.0"}
    payload = hashlib.sha256(str(manifest).encode()).hexdigest()
    signature = hmac.new(b"secret_key", payload.encode(), hashlib.sha256).hexdigest()
    
    assert verifier.verify_manifest(manifest, signature, "pub_1")

def test_signature_verification_failure():
    trust_keys = {"pub_1": "secret_key"}
    verifier = PluginSignatureVerifier(trust_keys)
    
    manifest = {"name": "test_plugin", "version": "1.0.0"}
    assert not verifier.verify_manifest(manifest, "wrong_sig", "pub_1")
    assert not verifier.verify_manifest(manifest, "any_sig", "unknown_pub")
