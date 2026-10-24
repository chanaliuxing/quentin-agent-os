import pytest
import os
import json
from pathlib import Path
from quentin.security.audit_chain import AuditChain

def test_audit_chain_persistence_and_integrity():
    p = Path("data/audit_chain.jsonl")
    if p.exists():
        p.unlink()
    
    chain = AuditChain(repo_root=".")
    
    # Sign events
    chain.sign_event("e1", {"data": "v1"})
    chain.sign_event("e2", {"data": "v2"})
    
    assert chain.chain_path.exists()
    assert chain.verify_integrity() is True

def test_audit_chain_tamper_detection():
    p = Path("data/audit_chain.jsonl")
    if p.exists():
        p.unlink()
        
    chain = AuditChain(repo_root=".")
    
    chain.sign_event("e1", {"data": "v1"})
    chain.sign_event("e2", {"data": "v2"})
    
    # Tamper with the file
    lines = chain.chain_path.read_text().splitlines()
    data = json.loads(lines[0])
    data["data"]["data"] = "TAMPERED" # Modify content
    lines[0] = json.dumps(data)
    chain.chain_path.write_text("\n".join(lines) + "\n")
    
    # Reload and verify
    new_chain = AuditChain(repo_root=".")
    assert new_chain.verify_integrity() is False
