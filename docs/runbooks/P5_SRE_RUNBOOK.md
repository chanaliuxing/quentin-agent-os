# P5 SRE Runbook

## SLOs and Error Budgets
- **Availability**: 99.9%
- **Latency**: P95 < 2s
- **Safety**: False Positive < 1%

## Handling Budget Exhaustion
When a budget is exhausted, the system enters **Degradation Mode**:
1. High-risk evolution tasks are suspended.
2. Concurrency limits are reduced.
3. System switches to more conservative models.

## Recovery
To exit degradation mode, manually reset the error budget after resolving the underlying issue:
- API endpoint: `POST /governance/budgets/reset` (to be implemented)
- Or restart the `brain_daemon`.
