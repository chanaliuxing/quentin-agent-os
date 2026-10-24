from __future__ import annotations
from enum import IntEnum
from dataclasses import dataclass, field
from typing import List, Dict, Any

class MaturityLevel(IntEnum):
    L0_MANUAL = 0
    L1_ASSISTED = 1
    L2_PARTIAL_AUTONOMY = 2
    L3_HIGH_AUTONOMY = 3
    L4_FULL_AUTONOMY = 4

@dataclass
class MaturityScore:
    level: MaturityLevel
    dimension_scores: Dict[str, float] # safety, reliability, governance, etc.
    gaps: List[str] = field(default_factory=list)
    evidence_hashes: List[str] = field(default_factory=list)
