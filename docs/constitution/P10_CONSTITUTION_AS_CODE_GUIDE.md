# P10 Constitution-as-Code Guide

## Immutable Zones
The Constitution defines paths that NO autonomous agent can modify. These are typically:
- `quentin/kernel/**`
- `quentin/constitution/**`
- `governance.yaml`

## Escalation Policies
Certain mutations require multi-admin approval as defined by the Constitution rules.

## Enforcement
The `ConstitutionEnforcer` runs as the final ring in the `SafetyKernel`. It operates at the binary level of path matching and cannot be disabled by policy tuning.
