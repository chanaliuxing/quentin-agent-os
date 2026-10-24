from __future__ import annotations
from typing import Dict, Any, List
from quentin.blueprint.domain_template_spec import DomainTemplateSpec

class DomainValidator:
    """
    P11-B: Domain Validator
    Validates that a domain meets organizational requirements.
    """
    def validate(self, spec: DomainTemplateSpec) -> List[str]:
        errors = []
        
        # 1. Check required modules
        if "security" not in spec.required_modules:
            errors.append("Missing required security module")
            
        # 2. Check risk policies
        if spec.policy_defaults.get("max_risk_level") == "critical" and spec.domain_name != "admin":
            errors.append("Critical risk level only allowed for admin domain")
            
        return errors
