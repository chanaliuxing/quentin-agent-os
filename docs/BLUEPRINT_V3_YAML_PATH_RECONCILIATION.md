# Blueprint v3 YAML Path Reconciliation

Date: 2026-02-07

This repo treats `blueprint.md` as the source-of-truth narrative and `blueprint/meta_agent_v3.yaml` as a machine-readable index.

The YAML file uses dotted paths that are intended to be stable import targets. Over time, canonical implementations moved
to different modules. To avoid breaking the blueprint index, we provide thin compatibility wrappers that re-export canonical
symbols, without changing the canonical implementations.

## Wrappers Added

- `quentin/planning/planner.py` re-exports `HierarchicalPlanner`
- `quentin/evaluation/harness.py` re-exports `EvalHarness`
- `quentin/research/*` re-exports L3 research symbols:
  - `ExperimentOrchestrator`
  - `EvolutionStrategyManager`
  - `BudgetController`
  - `PolicyEngine`
- `quentin/self_programming/manager.py` re-exports `SelfImprovementManager`
- `quentin/governance/council.py` provides `GovernanceCouncil` facade backed by `PatchGovernanceCouncil`
- `quentin/governance/constitution.py` provides `Constitution.load()` for structured `governance.yaml` access

## Verification

- Run `python scripts/blueprint_coverage_report.py` to ensure YAML sections are now evaluated (not all `planned`).
- Run `python scripts/run_evidence_audit.py --spec blueprint/meta_agent_v3_spec.json` for spec-based evidence.

