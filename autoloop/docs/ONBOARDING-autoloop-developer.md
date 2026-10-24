# Onboarding: AutoLoop Developer

## Adding a New Business Failure Type
1. Add normalization behavior in `app/metrics/business_failure_signature_normalizer.py`.
2. Update routing in `app/control/failure_router.py` and policy json.
3. Add replay sample to `tests/replay/business_failure_golden_pack/`.
4. Update playbook and taxonomy docs.
5. Run targeted tests + control-plane regression.

## Updating Recovery Rollout
1. Edit `policies/recovery_rollout_policy.json`.
2. Keep action fields complete:
   - `eligibility_rule`
   - `max_retry_budget`
   - `expected_terminal_state`
   - `rollback_rule`
3. Validate with `python scripts/run_recovery_canary.py`.

## Dossier-First Debugging
- Use `python scripts/dump_run_dossier.py --workflow-id <id>`.
- Diagnose from dossier and metrics reports before touching control-plane internals.

## Guardrails
- Do not expand `ci_control_plane_gate.sh` beyond control-plane checks.
- Do not change event/evidence schema without RFC update.
