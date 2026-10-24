# P5 Disaster Recovery Runbook

## Backup Strategy
- Critical paths are snapshotted to `data/backups/`.
- Snapshots include: `config/`, `blueprint/`, `governance.yaml`.

## Commands
- **Backup**: `python scripts/dr_backup.py`
- **Restore**: `python scripts/dr_restore.py <snapshot_id>`

## RPO/RTO
- **RPO**: 24 hours (default backup frequency).
- **RTO**: < 5 minutes (time to restore from local snapshot).
