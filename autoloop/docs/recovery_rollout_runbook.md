# Recovery Rollout Runbook

## Modes
- `shadow`: compute action only, never execute.
- `canary`: execute on sampled subset.
- `full`: execute for all eligible runs.

## Required Action Fields
- `eligibility_rule`
- `max_retry_budget`
- `expected_terminal_state`
- `rollback_rule`

## Release Sequence
1. Set policy mode to `shadow` and collect `runtime/metrics/recovery_canary_report.json`.
2. Move to `canary` at 5%-10% after two clean windows.
3. Move to `full` only if terminal-state mismatch stays below threshold for two windows.

## Codex Timeout Baseline
- Default real-run candidate: `CODEX_TIMEOUT_PROFILE=codex_balanced` (`90s/420s`).
- Keep `codex_fast` (`45s/180s`) for pressure regression.
- Use `codex_debug` (`120s/600s`) only for deep diagnosis windows.

## Low-Token Validation Cadence
- Small change: run `1` real codex validation.
- Important change: run `3` real codex validations.
- Default-profile promotion or major change: run `5` real codex validations.
- Rolling windows (`rolling-10`, `rolling-20`) use naturally accumulated real runs; do not batch-run only for statistics.
- Canary command:
  - `python scripts/run_codex_timeout_canary.py --prd-path ./blueprint.md --runs 3 --timeout-profile codex_balanced`

## Rollback
- If `terminal_state_expected_match_rate` drops or regression fails:
  - switch mode back to `shadow`,
  - archive canary report snapshot,
  - open follow-up on failed failure type.

## Owner Mapping
| Role | Responsibility |
| --- | --- |
| Taxonomy owner | Promote business failure enums and signatures |
| Recovery owner | Update rollout policy and playbook actions |
| Platform owner | Maintain gate scripts and regression coverage |

## Nightly Operations
- Run `scripts/run_business_failure_nightly.sh`.
- The nightly script now includes:
  - `run_agent_execution_remediation.py` for `AGENT_SUBPROCESS_NONZERO_EXIT` rolling analysis and ticketing.
  - Optional subprocess-only variant compare when `VARIANT_A` and `VARIANT_B` are set.
- Key outputs:
  - `runtime/metrics/agent_execution_remediation_report.json`
  - `runtime/hooks/execution_ticket_*.json`
