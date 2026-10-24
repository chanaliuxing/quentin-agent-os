# Onboarding: AutoLoop Operator

## Daily Checklist
- Run `python scripts/run_business_failure_monitor.py`.
- Check `runtime/metrics/business_failure_monitor_report.json`.
- If ticket generated, assign taxonomy owner and recovery owner.

## Weekly Checklist
- Run `python scripts/promote_business_taxonomy.py`.
- Review `runtime/metrics/business_failure_promotion_report.json`.
- Validate canary safety via `python scripts/run_recovery_canary.py`.
- Compare strategy variants via `python scripts/compare_agent_variants.py --variant-a <tagA> --variant-b <tagB>`.
- Run execution remediation monitor via `python scripts/run_agent_execution_remediation.py --window-size 20 --min-count 2 --min-ratio 0.2`.
- For planner nonzero-exit trends, use quick lens: `python scripts/compare_agent_variants.py --variant-a <tagA> --variant-b <tagB> --only-subprocess`.

## Incident Flow
1. Open run dossier: `python scripts/dump_run_dossier.py --workflow-id <id>`.
2. Confirm terminal/primary/secondary failures.
3. Apply corresponding playbook.
4. Re-run regression and verify gate green.

## Required Reports
- `control_plane_slo_report.json`
- `business_failure_monitor_report.json`
- `business_failure_promotion_report.json`
- `recovery_canary_report.json`
- `agent_execution_remediation_report.json`
