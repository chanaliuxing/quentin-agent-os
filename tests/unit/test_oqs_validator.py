import pytest
import yaml
from quentin.specs.oqs_validator import OQSValidator

def test_oqs_validator_logic(tmp_path):
    validator = OQSValidator()
    
    # 1. Valid Spec
    valid_spec = tmp_path / "valid.yaml"
    valid_spec.write_text("version: 1.0.0\nschemas: {Test: {type: object}}", encoding="utf-8")
    assert not validator.validate_spec(str(valid_spec))
    
    # 2. Invalid Spec (missing schemas)
    invalid_spec = tmp_path / "invalid.yaml"
    invalid_spec.write_text("version: 1.0.0", encoding="utf-8")
    errors = validator.validate_spec(str(invalid_spec))
    assert "Missing schemas" in errors[0]
