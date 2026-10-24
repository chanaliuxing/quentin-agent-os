from app.metrics.business_failure_signature_normalizer import (
    infer_taxonomy_candidate_name,
    normalize_business_failure_signature,
)


def test_normalize_business_failure_signature_with_events():
    signature = normalize_business_failure_signature(
        primary_failure_type="BUSINESS_REJECTION_UNMAPPED",
        first_failure_stage="unclassified_failure",
        missing_artifacts=[],
        grader_results={},
        failure_events=[{"cause_type": "MISSING_REQUIRED_TEST"}],
    )
    assert signature == "business_rejection_unmapped:unclassified_failure:events:missing_required_test"


def test_infer_taxonomy_candidate_name_is_stable():
    candidate = infer_taxonomy_candidate_name(
        signature="business_evidence_missing:acceptance_contract_failed:grader:contract_validator:fail",
        primary_failure_type="BUSINESS_EVIDENCE_MISSING",
    )
    assert candidate == "BUSINESS_EVIDENCE_MISSING_ACCEPTANCE_CONTRACT_FAILED_GRADER_CONTRACT_VALIDATOR_FAIL"
