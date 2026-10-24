import pytest

from app.models import AgentRole, validate_output_contract


def test_validate_dev_contract():
    payload = """
    {
      "contract_version": "1.0",
      "generated_at": "2026-02-26T00:00:00",
      "module_name": "m1",
      "status": "success",
      "files_changed": ["a.py"],
      "implementation_notes": "ok"
    }
    """
    contract = validate_output_contract(AgentRole.DEV, payload)
    assert contract.module_name == "m1"


def test_validate_qa_contract():
    payload = """
    {
      "contract_version": "1.0",
      "generated_at": "2026-02-26T00:00:00",
      "module_name": "m1",
      "status": "pass",
      "tests_run": 3,
      "tests_passed": 3,
      "tests_failed": 0,
      "issues": []
    }
    """
    contract = validate_output_contract(AgentRole.QA, payload)
    assert contract.tests_passed == 3


def test_validate_reviewer_contract_requires_finding_codes_for_revision():
    payload = """
    {
      "contract_version": "1.0",
      "generated_at": "2026-02-26T00:00:00",
      "module_name": "m1",
      "verdict": "needs_revision",
      "findings": ["missing test binding"],
      "finding_codes": []
    }
    """
    with pytest.raises(Exception):
        validate_output_contract(AgentRole.REVIEWER, payload)


def test_validate_reviewer_contract_with_finding_codes_passes():
    payload = """
    {
      "contract_version": "1.0",
      "generated_at": "2026-02-26T00:00:00",
      "module_name": "m1",
      "verdict": "needs_revision",
      "findings": ["missing test binding"],
      "finding_codes": ["MISSING_TEST_BINDING"]
    }
    """
    contract = validate_output_contract(AgentRole.REVIEWER, payload)
    assert contract.verdict == "needs_revision"


def test_invalid_contract_raises():
    payload = "{\"module_name\": \"m1\"}"
    with pytest.raises(Exception):
        validate_output_contract(AgentRole.DEV, payload)
