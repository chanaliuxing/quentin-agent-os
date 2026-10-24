import pytest
import os
import json
from pathlib import Path
from quentin.security.audit_schema import AuditEvent as SecurityAuditEvent
from quentin.kernel.audit import default_audit_logger

def test_security_audit_logging_logic():
    # Force enable P3 Audit flag for this test
    os.environ["FF_P3_AUDIT_V1"] = "1"
    
    logger = default_audit_logger()
    sec_path = logger.security_path
    if sec_path.exists():
        sec_path.unlink()
        
    event = SecurityAuditEvent(
        event_id="test-id",
        actor="test-actor",
        action="test-action",
        resource="test-resource",
        decision="allow",
        reason="test-reason"
    )
    
    logger.append(event)
    
    assert sec_path.exists()
    with sec_path.open("r") as f:
        line = f.readline()
        data = json.loads(line)
        assert data["event_id"] == "test-id"
        assert data["decision"] == "allow"

def test_security_audit_disabled_by_default():
    # Ensure flag is OFF
    os.environ["FF_P3_AUDIT_V1"] = "0"
    
    logger = default_audit_logger()
    sec_path = logger.security_path
    if sec_path.exists():
        sec_path.unlink()
        
    event = SecurityAuditEvent(
        event_id="test-disabled",
        actor="test-actor",
        action="test-action",
        resource="test-resource",
        decision="block",
        reason="test-reason"
    )
    
    logger.append(event)
    
    # It should NOT exist in the security audit log if flag is off
    assert not sec_path.exists()
