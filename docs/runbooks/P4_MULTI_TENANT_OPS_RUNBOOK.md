# P4 Multi-Tenant Operations Runbook

## Overview
This runbook covers the management of multi-tenant resource isolation and concurrency quotas.

## Quota Management
- Default tenant quota is 5 concurrent tasks.
- Quotas are managed via `LanePolicy`.
- Global circuit breaker trips at 100 concurrent tasks across all tenants.

## Troubleshooting 429 Errors
- If a tenant receives a 429 (Too Many Requests), check their current concurrency.
- Adjust quotas using `lane_orchestrator.policy.update_quota(tenant_id, new_limit)`.

## Monitoring
- Monitor `current_global_concurrency` to avoid tripping the circuit breaker.
- Check `tenant_quotas` for outliers or heavy users.
