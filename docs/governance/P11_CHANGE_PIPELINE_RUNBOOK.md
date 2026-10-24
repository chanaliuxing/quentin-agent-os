# P11 Change Governance Pipeline Runbook

## Change Lifecycle
1. **Request**: Submit via `POST /governance/changes`.
2. **Analysis**: Automated impact and risk assessment.
3. **Approval**: Multi-step human-in-the-loop approval.
4. **Promotion**: Rollout to nodes via `POST /governance/changes/{id}/promote`.

## Rollback
If a change causes regression:
1. Identify the `change_id`.
2. Execute the `rollback_plan` as defined in the request.
3. Mark status as `rolled_back`.
