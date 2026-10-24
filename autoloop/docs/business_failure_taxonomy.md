# Business Failure Taxonomy

## Frozen Scope
- This taxonomy consumes control-plane facts only:
  - `primary_failure_type`
  - `secondary_failure_types`
  - `failure_events`
- `terminal_state`
- No recovery rule may read raw runner logs as first source.

## Priority Failure Types
- `MISSING_REQUIRED_TEST`
- `GRADER_FAILED`
- `BUSINESS_REJECTION_UNMAPPED`
- `BUSINESS_EVIDENCE_MISSING`
- `BUSINESS_TEST_POLICY_GAP`
- `BUSINESS_GRADER_CONTRACT_GAP`

## Type Definitions
- `MISSING_REQUIRED_TEST`
  - Meaning: required test gates are not satisfied by current outputs.
  - Evidence source: acceptance event + missing required tests list.
- `GRADER_FAILED`
  - Meaning: configured grader returns `fail` with structured detail.
  - Evidence source: grader event and failure detail.
- `BUSINESS_REJECTION_UNMAPPED`
  - Meaning: business rejection exists but cannot be mapped to a concrete policy/test/grader bucket.
  - Evidence source: `primary_failure_type` promotion from legacy `UNCLASSIFIED_BUSINESS_FAILURE`.
- `BUSINESS_EVIDENCE_MISSING`
  - Meaning: rejection occurred with insufficient structured evidence for deterministic classification.
  - Evidence source: no valid business candidates + rejected acceptance.
- `BUSINESS_TEST_POLICY_GAP`
  - Meaning: test policy contract exists but binding/coverage is incomplete.
  - Evidence source: `required_test_missing` or acceptance failure types containing `MISSING_REQUIRED_TEST`.
- `BUSINESS_GRADER_CONTRACT_GAP`
  - Meaning: grader contract mismatch despite produced artifacts.
  - Evidence source: `grader_failed` stage or acceptance failure type `GRADER_FAILED`.

## Upgrade Rule
- If the same `BUSINESS_REJECTION_UNMAPPED` or `BUSINESS_EVIDENCE_MISSING` pattern appears in 2 consecutive runs:
  - Create a new formal failure enum.
  - Add router policy action.
  - Add playbook and matrix case.
  - Add one acceptance test asserting expected terminal state.
  - Add a rerun gate condition documenting when retry is allowed.

## Non-overwrite Rule
- Existing business primary cause must never be replaced by shutdown or timeout labels.
- Execution/environment labels are appended as secondary semantics.

## Routing Defaults
- `MISSING_REQUIRED_TEST` -> `replan_from_spec` with test binding repair.
- `GRADER_FAILED` -> `replan_from_spec` with grader mismatch repair.
- `BUSINESS_TEST_POLICY_GAP` -> `replan_from_spec` with test-policy patch.
- `BUSINESS_GRADER_CONTRACT_GAP` -> `replan_from_spec` with grader-contract patch.
- `BUSINESS_REJECTION_UNMAPPED` -> `taxonomy_review_required` before next phase.
- `BUSINESS_EVIDENCE_MISSING` -> `taxonomy_review_required` before next phase.

## Agent Execution Failure Taxonomy
- `AGENT_SUBPROCESS_NONZERO_EXIT` -> `replan_from_spec` with subprocess exit triage.
- `AGENT_OUTPUT_MISSING` -> `replan_from_spec` with output persistence checks.
- `AGENT_CONTRACT_VIOLATION` -> `replan_from_spec` with contract/schema repair.
- `AGENT_ARTIFACT_WRITE_FAILED` -> `replan_from_spec` with artifact write guardrails.
- `AGENT_RUNNER_SESSION_DEGRADED` -> `replan_from_spec` with runner/session health repair.
- `AGENT_RESULT_PARSE_FAILED` -> `replan_from_spec` with output JSON parse hardening.

`AGENT_EXECUTION_FAILED` is retained only as fallback parent when subtype mapping is not possible.
