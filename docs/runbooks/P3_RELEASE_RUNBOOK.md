# P3 Release Runbook

## Pre-Flight
1. Run `python3 tests/manual/system_integrity_auditor.py` -> All Green.
2. Check `config/openclaw_parity.yaml` -> Flags match intent.

## Release Steps
1. Run `python3 scripts/release_promote.py --target staging`
2. Verify logs for "Promoted to staging".
3. Run integration tests.
4. Run `python3 scripts/release_promote.py --target prod`

## Rollback
1. Run `python3 scripts/release_rollback.py --id <snap_id>`
2. Verify config restored.
