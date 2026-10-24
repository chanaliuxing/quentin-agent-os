# Recovery Playbooks

## Source of Truth
- Playbooks consume only control-plane artifacts:
  - `runtime/evidence/<workflow_id>/<phase_id>/execution_summary.json`
  - `runtime/event_log/<workflow_id>/<phase_id>/events.jsonl`

## Global Rules
- Do not overwrite `primary_failure_type` once set by a business failure event.
- Add execution/environment issues as `secondary_failure_types` only.
- A recovery action is complete only after rerun updates `WORKFLOW_TERMINATED` and `terminal_state`.
- Playbook routing reads only `primary_failure_type`, `failure_events`, `terminal_state`.
- Exit condition is mandatory for every playbook; unresolved exit condition escalates to `taxonomy_review_required`.

## `MISSING_REQUIRED_TEST`
- Evidence inputs:
  - `primary_failure_type=MISSING_REQUIRED_TEST`
  - `failure_events[].failure_type=MISSING_REQUIRED_TEST`
- Repair action:
  - Rebuild task spec test bindings (`required_tests`, `allowed_paths`).
  - Regenerate missing tests and rerun acceptance.
- Success criteria:
  - `primary_failure_type` no longer `MISSING_REQUIRED_TEST`.
  - Acceptance status is `passed` or a different classified failure.
- Rerun condition:
  - Trigger rerun only after `required_tests` and `allowed_paths` are both updated in generated task/spec artifacts.
- Exit condition:
  - If this failure repeats 2 times consecutively, promote to `BUSINESS_TEST_POLICY_GAP` and open taxonomy review.

## `REQUIRED_TEST_FAILED`
- Evidence inputs:
  - `primary_failure_type=REQUIRED_TEST_FAILED`
  - `failed_required_tests` is non-empty
  - `required_test_failure_details` contains actionable failure lines
- Repair action:
  - Prioritize implementation fixes if failure lines reference target module code paths.
  - Prioritize test-baseline fixes if failure lines show mock/test harness contract drift.
  - Keep scope constrained to failing required test set; do not broaden to unrelated suites.
- Success criteria:
  - `failed_required_tests` becomes empty on rerun.
  - `required_test_outcomes` shows all required tests as `passed`.
- Rerun condition:
  - Trigger rerun only after patch references at least one failing test and one related source/test file.
- Exit condition:
  - If this failure repeats 2 times with identical failure details, escalate to `BUSINESS_TEST_POLICY_GAP`.

## `GRADER_FAILED`
- Evidence inputs:
  - `primary_failure_type=GRADER_FAILED`
  - Grader detail in `failure_events[].payload`
- Repair action:
  - Align outputs to grader contract fields.
  - Rerun grader and acceptance.
- Success criteria:
  - `GRADER_FAILED` absent from primary and secondary failures.
  - Acceptance status progresses to `passed` or another classified cause.
- Rerun condition:
  - Trigger rerun only after grader contract payload keys are present in generated outputs.
- Exit condition:
  - If this failure repeats 2 times consecutively, promote to `BUSINESS_GRADER_CONTRACT_GAP` and open taxonomy review.

## `BUSINESS_REJECTION_UNMAPPED`
- Evidence inputs:
  - `primary_failure_type=BUSINESS_REJECTION_UNMAPPED`
  - Terminal state is `REJECTED`
- Repair action:
  - Start taxonomy review.
  - Promote pattern to a formal enum when repeated twice.
  - Add matrix scenario and playbook entry for new enum.
- Success criteria:
  - Subsequent runs classify same pattern with a formal business enum.
  - `unknown_failure_rate` stays at `0.0`.
- Exit condition:
  - If taxonomy review cannot map the pattern in current phase, hard-stop next phase promotion.

## `BUSINESS_EVIDENCE_MISSING`
- Evidence inputs:
  - `primary_failure_type=BUSINESS_EVIDENCE_MISSING`
  - `failure_events` missing concrete business failure entries
- Repair action:
  - Backfill structured failure evidence (`failure_type`, `stage`, `event_time`) at source stage.
  - Rerun acceptance after evidence instrumentation update.
- Success criteria:
  - Primary failure is a concrete business enum (not evidence-missing).
- Exit condition:
  - If repeated twice, block promotion and require integrator review before rerun.

## `AGENT_SUBPROCESS_NONZERO_EXIT`
- Evidence inputs:
  - `primary_failure_type=AGENT_SUBPROCESS_NONZERO_EXIT`
  - `failure_events[].payload.subprocess_detail` contains:
    - `exit_code`
    - `execution_mode`
    - `session_source`
    - `stderr_tail` / `stdout_tail`
- Repair action:
  - Fix runner command/env assumptions and rerun target agent stage.
  - Prioritize by `agent_execution_failure_breakdown_report.subprocess_nonzero_exit_breakdown.by_stage`.
  - Stage-aware routing:
    - `planner/reviewer` stage -> `retry_same_plan` (quick retry before full replan)
    - `dev/qa` stage -> `replan_from_spec`
- Success criteria:
  - Primary failure no longer equals `AGENT_SUBPROCESS_NONZERO_EXIT`.

## `AGENT_OUTPUT_MISSING`
- Evidence inputs:
  - `primary_failure_type=AGENT_OUTPUT_MISSING`
  - Empty output payload in stage result.
- Repair action:
  - Enforce result write contract and validate output file persistence.
- Success criteria:
  - Stage emits non-empty, contract-parseable output.

## `AGENT_CONTRACT_VIOLATION`
- Evidence inputs:
  - `primary_failure_type=AGENT_CONTRACT_VIOLATION`
  - Contract validation/repair events show schema mismatch.
- Repair action:
  - Patch agent prompt contract and rerun contract validator.
- Success criteria:
  - Contract validator passes and failure type changes.

## `AGENT_ARTIFACT_WRITE_FAILED`
- Evidence inputs:
  - `primary_failure_type=AGENT_ARTIFACT_WRITE_FAILED`
  - Result artifact missing or write not persisted.
- Repair action:
  - Fix write path/permission and rerun stage with artifact presence gate.
- Success criteria:
  - Required result artifact exists and is non-empty.

## `AGENT_RUNNER_SESSION_DEGRADED`
- Evidence inputs:
  - `primary_failure_type=AGENT_RUNNER_SESSION_DEGRADED`
  - State/session degradation signals in failure events.
- Repair action:
  - Rebuild session state path, then rerun in `codex_balanced`.
- Success criteria:
  - No session degradation signal on rerun.

## `AGENT_RESULT_PARSE_FAILED`
- Evidence inputs:
  - `primary_failure_type=AGENT_RESULT_PARSE_FAILED`
  - Output cannot be parsed into contract JSON.
- Repair action:
  - Tighten output-format instruction and rerun with parser guard.
- Success criteria:
  - Parser succeeds and failure type no longer parse-related.
