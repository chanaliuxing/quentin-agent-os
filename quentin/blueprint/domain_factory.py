from __future__ import annotations
import os
from pathlib import Path
from typing import Dict, Any
from quentin.blueprint.domain_template_spec import DomainTemplateSpec

class DomainFactory:
    """
    P11-B: Domain Factory
    Generates new domain scaffolding.
    """
    def __init__(self, repo_root: str = ".") -> None:
        self.repo_root = Path(repo_root).resolve()

    def generate_domain(self, spec: DomainTemplateSpec) -> str:
        domain_path = self.repo_root / "quentin" / "domains" / spec.domain_name
        domain_path.mkdir(parents=True, exist_ok=True)
        
        # 1. Generate __init__.py
        (domain_path / "__init__.py").touch()
        
        # 2. Generate config skeleton
        config_path = domain_path / "config.yaml"
        config_path.write_text(f"domain: {spec.domain_name}\npolicy: {spec.policy_defaults}\n", encoding="utf-8")
        
        # 3. Generate test scaffolding
        test_path = self.repo_root / "tests" / "domains" / f"test_{spec.domain_name}.py"
        test_path.parent.mkdir(parents=True, exist_ok=True)
        test_path.write_text(f"def test_{spec.domain_name}_baseline():\n    assert True\n", encoding="utf-8")
        
        return str(domain_path)
