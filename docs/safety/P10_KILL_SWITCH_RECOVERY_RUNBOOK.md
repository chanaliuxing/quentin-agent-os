# P10 Kill-Switch & Recovery Runbook

## Triggering Kill-Switch
If a domain or node exhibits anomalous behavior:
`POST /safety/kill-switch/trigger?scope=domain:web`

This will immediately block all tool calls and evolution in that domain.

## Recovery Workflow
1. Isolate the affected scope.
2. Rollback to the last known-good snapshot.
3. Validate baseline performance.
4. Release kill-switch: `POST /safety/kill-switch/release?scope=domain:web`
