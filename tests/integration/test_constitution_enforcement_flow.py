import pytest
from quentin.constitution.dsl import ConstitutionDSL, ConstitutionRule
from quentin.constitution.enforcer import ConstitutionEnforcer

def test_constitution_enforcement_blocking():
    dsl = ConstitutionDSL()
    dsl.add_law(ConstitutionRule("L1", "immutable_zone", "quentin/kernel", "block"))
    enforcer = ConstitutionEnforcer(dsl)
    
    # 1. Block attempt to mutate protected zone
    assert enforcer.validate_mutation("quentin/kernel/safety.py") is False
    
    # 2. Allow mutation in safe zone
    assert enforcer.validate_mutation("quentin/utils/helper.py") is True
