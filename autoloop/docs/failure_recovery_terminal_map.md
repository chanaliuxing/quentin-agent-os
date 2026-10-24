# Failure-Recovery-Terminal Map

| Failure Type | Recovery Action | Expected Terminal State |
| --- | --- | --- |
| `MISSING_REQUIRED_TEST` | `replan_from_spec` | `REJECTED` |
| `GRADER_FAILED` | `replan_from_spec` | `REJECTED` |
| `BUSINESS_TEST_POLICY_GAP` | `replan_from_spec` | `REJECTED` |
| `BUSINESS_GRADER_CONTRACT_GAP` | `replan_from_spec` | `REJECTED` |
| `BUSINESS_REJECTION_UNMAPPED` | `taxonomy_review_required` | `REJECTED` |
| `BUSINESS_EVIDENCE_MISSING` | `taxonomy_review_required` | `REJECTED` |

## Validation Rule
- Any change to failure routing must keep this table and `app/control/failure_router.py` in sync.
- CI validation asserts known mappings through unit tests.
