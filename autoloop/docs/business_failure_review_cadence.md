# Business Failure Review Cadence

## Scope
- This cadence governs only business-failure convergence.
- Control-plane protocol and `ci_control_plane_gate.sh` remain frozen.

## Weekly Cycle
- Every Monday: review `runtime/metrics/business_failure_monitor_report.json`.
- Every Wednesday: review `runtime/metrics/business_failure_promotion_report.json`.
- Every Friday: close or escalate open `taxonomy_ticket_*.json`.

## Upgrade Rules
- If `BUSINESS_REJECTION_UNMAPPED` or `BUSINESS_EVIDENCE_MISSING` appears in 2 consecutive rolling windows:
  - promote to formal taxonomy enum,
  - add router action and playbook entry,
  - add replay golden sample.
- If no stable signature exists, keep `BUSINESS_EVIDENCE_MISSING` and open instrumentation fix task.

## Owners
- Taxonomy owner: upgrades failure enums.
- Recovery owner: maintains playbooks and rollout policy.
- Platform owner: keeps control-plane gate and regressions green.
