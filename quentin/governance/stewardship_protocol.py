from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Dict, Any

@dataclass
class CouncilProposal:
    id: str
    title: str
    proposed_by: str
    votes_for: List[str] = field(default_factory=list)
    votes_against: List[str] = field(default_factory=list)
    status: str = "open" # "open", "passed", "rejected"

class StewardshipCouncil:
    """
    P12-D: Stewardship Council Protocol
    Decentralized governance for OQS evolution.
    """
    def __init__(self, member_nodes: List[str]) -> None:
        self.members = member_nodes
        self.proposals: Dict[str, CouncilProposal] = {}

    def vote(self, proposal_id: str, member_id: str, approve: bool) -> bool:
        if member_id not in self.members:
            return False
        
        prop = self.proposals.get(proposal_id)
        if not prop or prop.status != "open":
            return False
            
        if approve:
            prop.votes_for.append(member_id)
        else:
            prop.votes_against.append(member_id)
            
        # Decision threshold (e.g., > 50% members)
        if len(prop.votes_for) > len(self.members) / 2:
            prop.status = "passed"
            
        return True
