import pytest
from quentin.constitution.dsl import ConstitutionDSL, ConstitutionRule
from quentin.constitution.compiler import ConstitutionCompiler

def test_constitution_compilation():
    dsl = ConstitutionDSL()
    dsl.add_law(ConstitutionRule("L1", "immutable_zone", "quentin/kernel", "block"))
    
    compiler = ConstitutionCompiler()
    compiled = compiler.compile(dsl)
    
    assert len(compiled["immutable_zone"]) == 1
    
    # Test the closure
    check_law = compiled["immutable_zone"][0]
    assert check_law("quentin/kernel/safety.py") is True
    assert check_law("quentin/utils/helpers.py") is False
