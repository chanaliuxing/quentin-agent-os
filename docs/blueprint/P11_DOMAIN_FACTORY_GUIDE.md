# P11 Domain Factory Guide

## Creating a New Domain
Use the `DomainFactory` to scaffold a new domain that adheres to organizational standards.

1. Define a `DomainTemplateSpec`.
2. Ensure `security` and `observability` modules are included.
3. Run the generator to produce the `quentin/domains/{name}` structure.

## Governance Requirements
All new domains must include:
- A `config.yaml` with default risk policies.
- Baseline test scaffolding.
- SLO definitions in the global registry.
