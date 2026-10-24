# P11 Operations Control Tower Runbook

## Global Overview
The Control Tower provides a centralized view of system health, SLO budgets, and active risks.
Access via: `GET /ops/control-tower/overview`

## Incident Response
1. Monitor `active_risks` list via the API or dashboard.
2. If an SLO budget is exhausted, the system automatically enters degradation mode.
3. Investigate the cause using the `p3_audit` logs and `data/security_audit.jsonl`.

## Risk Management
- **High Severity**: Immediate human intervention required.
- **Medium Severity**: Backlog check within 24 hours.
