# P12 Ecosystem Certification Kit Guide

## Running Certification
`python scripts/ecosystem_run_certification.py --target node-id`

## Criteria
1. **API Compatibility**: Must implement OQS `1.0.0`.
2. **Safety**: Must have a functional `SafetyKernel` active.
3. **Traceability**: Must provide valid audit chain head.

## Verification
Valid certificates are stored in the `CertificationRegistry` and can be checked via the federation control plane.
