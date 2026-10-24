from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Dict, Any

@dataclass
class ConstitutionRule:
    id: str
    logic_type: str # "immutable_zone", "escalation", "forbidden_mutation"
    pattern: str
    action: str # "block", "escalate", "notify"

class ConstitutionDSL:
    """
    P10-A: Constitution-as-Code DSL
    Expresses the fundamental, immutable laws of the OS.
    """
    def __init__(self) -> None:
        self.laws: List[ConstitutionRule] = []

    def add_law(self, rule: ConstitutionRule) -> None:
        self.laws.append(rule)

    def get_laws_by_type(self, logic_type: str) -> List[ConstitutionRule]:
        return [L for l in self.laws if L.logic_type == logic_type]
