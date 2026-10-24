# P5 Compliance Runbook

## Data Classification
- **Public**: Safe for external sharing.
- **Internal**: Project team only.
- **Sensitive**: PII or API keys (Redacted).
- **Restricted**: Critical infrastructure (Highly restricted access).

## Redaction Pipeline
The `RedactionPipeline` automatically masks:
- API Keys (OpenAI, Google, Slack)
- Emails
- Passwords

## Audit Chain
All security events are signed in the `AuditChain`.
To verify integrity:
- Run `scripts/verify_audit_integrity.py` (to be implemented).
