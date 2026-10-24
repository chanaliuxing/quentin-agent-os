# ACCEPTANCE: Agent Execution Failure Decomposition

- [ ] `AGENT_EXECUTION_FAILED` no longer primary dominant failure in rolling-20 real codex runs.
- [ ] New subtype failures route to deterministic recovery actions (`replan_from_spec`).
- [ ] `runtime/metrics/agent_execution_failure_breakdown_report.json` generated in nightly.
- [ ] Execution subtype replay goldens pass in CI/nightly.
- [ ] Control-plane SLO gate semantics unchanged.

## Promotion Rule
- Promote when rolling-20 shows:
  - `AGENT_EXECUTION_FAILED` parent ratio trending down,
  - subtype coverage trending up,
  - no increase in `GLOBAL_TIMEOUT`.
- Top2 deep-dive gate:
  - `AGENT_OUTPUT_MISSING` and `AGENT_RESULT_PARSE_FAILED` appear as explicit subtypes in rolling windows,
  - their recovery match metrics are present in both:
    - `runtime/metrics/agent_execution_failure_breakdown_report.json`
    - `runtime/metrics/recovery_canary_report.json`
