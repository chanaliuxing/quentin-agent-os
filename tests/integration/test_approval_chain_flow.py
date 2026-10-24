import pytest
from quentin.governance.approval_chain import ApprovalChain

def test_approval_flow():
    chain = ApprovalChain()
    req_id = chain.create_request("deploy", "high", "dev1")
    
    assert chain.get_status(req_id) == "pending"
    
    # 1. Operator approval (not enough)
    chain.approve(req_id, "operator")
    assert chain.get_status(req_id) == "pending"
    
    # 2. Second operator approval (enough)
    chain.approve(req_id, "operator")
    assert chain.get_status(req_id) == "approved"

def test_admin_override():
    chain = ApprovalChain()
    req_id = chain.create_request("nuke", "critical", "dev1")
    
    chain.approve(req_id, "admin")
    assert chain.get_status(req_id) == "approved"
