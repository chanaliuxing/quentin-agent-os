# P7 Federation Operations Runbook

## Node Registration
To add a new node:
1. Deploy Quentin instance.
2. Call `node_registry.register_node()` with unique ID and endpoint.
3. Verify status is "active".

## Quarantine Procedure
If a node behaves maliciously:
1. Identify `node_id`.
2. Call `node_registry.quarantine_node(node_id)`.
3. Node will be excluded from task routing and sync.

## Sync Safety
- Only "safe" keys (model configs, metrics) are synced by default.
- Secrets and PII are filtered by `SyncFilter`.
