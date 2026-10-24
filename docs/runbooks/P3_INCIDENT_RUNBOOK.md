# P3 Incident Runbook

## Scenario 1: Failover Storm
- **Symptom**: High rate of `Failover triggered` logs.
- **Action**: Check `data/metrics/daily_stats.json`. If cost spikes, disable high-cost providers via `config/auth_profiles.json`.

## Scenario 2: Lane Deadlock
- **Symptom**: `lane_queue_wait_ms` > 10s.
- **Action**: Restart instance. Check `data/traces` for stuck locks.

## Scenario 3: Gateway Backlog
- **Symptom**: API 503.
- **Action**: Check `p3_metrics.py` snapshot. Scale workers if needed.
