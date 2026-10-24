from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from datetime import datetime

@dataclass
class PatchProposal:
    """
    A proposal for a code patch.
    """
    id: str
    target_files: List[str]
    diff: str
    intent: str
    created_at: datetime = field(default_factory=datetime.utcnow)
    status: str = "proposed"
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    # Optional: Evaluation/Test results
    eval_metrics: Dict[str, Any] = field(default_factory=dict)
    
    # Optional: Stats for safety check
    diff_stats: Dict[str, Any] = field(default_factory=dict)

    def get_unified_diff(self) -> str:
        return self.diff

@dataclass
class BlueprintPatchProposal(PatchProposal):
    """
    A proposal for modifying the blueprint documentation/spec.
    """
    pass
