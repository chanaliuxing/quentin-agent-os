from __future__ import annotations
import uuid
from dataclasses import dataclass, field
from typing import Dict, List, Optional

@dataclass
class ApprovalRequest:
    request_id: str
    action_type: str
    risk_level: str
    requester: str
    status: str = "pending" # "pending", "approved", "rejected"
    approvals: List[str] = field(default_factory=list) # List of approver roles

class ApprovalChain:
    """
    P7-C: Approval Chain Engine
    """
    def __init__(self) -> None:
        self.requests: Dict[str, ApprovalRequest] = {}

    def create_request(self, action_type: str, risk_level: str, requester: str) -> str:
        req_id = uuid.uuid4().hex
        self.requests[req_id] = ApprovalRequest(req_id, action_type, risk_level, requester)
        return req_id

    def approve(self, request_id: str, approver_role: str) -> bool:
        req = self.requests.get(request_id)
        if not req:
            return False
        
        req.approvals.append(approver_role)
        
        # Simple policy: 1 admin approval or 2 operator approvals
        if "admin" in req.approvals:
            req.status = "approved"
        elif req.approvals.count("operator") >= 2:
            req.status = "approved"
            
        return True

    def get_status(self, request_id: str) -> str:
        req = self.requests.get(request_id)
        return req.status if req else "unknown"
