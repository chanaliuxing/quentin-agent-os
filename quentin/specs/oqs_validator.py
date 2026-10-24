from __future__ import annotations
import yaml
from pathlib import Path
from typing import Dict, Any, List

class OQSValidator:
    """
    P12-A: Open Quentin Spec Validator
    Validates that definitions meet OQS standards.
    """
    def validate_spec(self, spec_path: str) -> List[str]:
        p = Path(spec_path)
        if not p.exists():
            return [f"Spec file not found: {spec_path}"]
        
        try:
            data = yaml.safe_load(p.read_text(encoding="utf-8"))
            if not data or "version" not in data:
                return ["Missing version in OQS spec"]
            
            if "schemas" not in data:
                return ["Missing schemas section in OQS spec"]
                
            return [] # Valid
        except Exception as e:
            return [f"YAML Parse error: {str(e)}"]
