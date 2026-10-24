# P7 Org Governance Runbook

## Roles
- **Operator**: Daily ops, 2 approvals needed for high risk.
- **Admin**: Full access, 1 approval needed for any risk.
- **Auditor**: Read-only access to audit logs.

## Approval Policy
- Low risk: Auto-approved.
- High risk: Requires 2 Operators or 1 Admin.
- Critical risk: Requires 1 Admin.

## Audit Reports
Run `scripts/export_org_audit_report.py` to generate quarterly compliance reports.
