# TODO: Decompose `AGENT_EXECUTION_FAILED`

- [x] Promote `codex_balanced` as default timeout profile (`90/420`).
- [x] Add execution subtype taxonomy:
  - `AGENT_SUBPROCESS_NONZERO_EXIT`
  - `AGENT_OUTPUT_MISSING`
  - `AGENT_CONTRACT_VIOLATION`
  - `AGENT_ARTIFACT_WRITE_FAILED`
  - `AGENT_RUNNER_SESSION_DEGRADED`
  - `AGENT_RESULT_PARSE_FAILED`
- [x] Wire subtype actions into `failure_router_policy`.
- [x] Keep `AGENT_EXECUTION_FAILED` as fallback parent only.
- [x] Add rolling breakdown report: `agent_execution_failure_breakdown_report.json`.
- [x] Add replay goldens for execution subtypes and include in nightly.
- [x] Keep control-plane gate unchanged.
