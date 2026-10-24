from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional

@dataclass
class ConstraintRule:
    rule_id: str
    action_type: str
    forbidden_scopes: List[str] = field(default_factory=list)
    environment_constraints: List[str] = field(default_factory=list)
    escalation_required: bool = False

class ConstraintDSL:
    """
    P5-D: Policy Constraint DSL
    Expresses boundaries for autonomous actions.
    """
    def __init__(self) -> None:
        self.rules: Dict[str, ConstraintRule] = {}
        self._bootstrap_defaults()

    def _bootstrap_defaults(self) -> None:
        # Core Domain Rule: No modifying Safety or Governance without escalation
        self.add_rule(ConstraintRule(
            rule_id="core_integrity",
            action_type="code_patch",
            forbidden_scopes=["quentin/kernel/safety.py", "governance.yaml"],
            escalation_required=True
        ))
        
        # Legal Domain Rule: Restricted to legal environment only
        self.add_rule(ConstraintRule(
            rule_id="legal_boundary",
            action_type="tool_call",
            environment_constraints=["legal_sandbox"],
            escalation_required=True
        ))

    def add_rule(self, rule: ConstraintRule) -> None:
        self.rules[rule.rule_id] = rule

    def get_rules_for_action(self, action_type: str) -> List[ConstraintRule]:
        return [r for r in self.rules.values() if r.action_type == action_type]
