from __future__ import annotations
from typing import List, Dict, Any
from quentin.policy.constraint_dsl import ConstraintDSL, ConstraintRule

class ConstraintVerifier:
    """
    P5-D: Policy Constraint Verifier
    Validates actions against the Constraint DSL rules.
    """
    def __init__(self, dsl: ConstraintDSL) -> None:
        self.dsl = dsl

    def verify_action(self, action_type: str, action_data: Dict[str, Any]) -> bool:
        rules = self.dsl.get_rules_for_action(action_type)
        for rule in rules:
            if not self._check_rule(rule, action_data):
                return False
        return True

    def _check_rule(self, rule: ConstraintRule, data: Dict[str, Any]) -> bool:
        # Check forbidden scopes
        target = data.get("target", "")
        for scope in rule.forbidden_scopes:
            if scope in target:
                return False
        
        # Check environment constraints
        env = data.get("environment", "")
        if rule.environment_constraints and env not in rule.environment_constraints:
            return False
            
        return True
