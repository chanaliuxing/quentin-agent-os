from __future__ import annotations
from typing import List, Dict, Any, Callable
from quentin.constitution.dsl import ConstitutionDSL, ConstitutionRule

class ConstitutionCompiler:
    """
    P10-A: Constitution Compiler
    Compiles DSL laws into executable runtime checks.
    """
    def compile(self, dsl: ConstitutionDSL) -> Dict[str, List[Callable]]:
        compiled_rules: Dict[str, List[Callable]] = {
            "immutable_zone": [],
            "forbidden_mutation": []
        }
        
        for law in dsl.laws:
            if law.logic_type == "immutable_zone":
                # Create a closure for path matching
                def check_path(path: str, law_pattern=law.pattern) -> bool:
                    return law_pattern in path
                compiled_rules["immutable_zone"].append(check_path)
                
        return compiled_rules
