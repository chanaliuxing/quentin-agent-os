# Reviewer Task - phase_01

## Module
module_main

## Your Tasks
1. Review planner plan quality
2. Return approved or needs_revision
3. Provide concrete findings list
4. Provide machine-readable `finding_codes` (e.g. PATH_CONFLICT, MISSING_TEST_BINDING, CONTRACT_MISMATCH)

## Typed Contracts
- TaskSpec: ./autoloop/phases_real6/phase_01/tasks/contracts/module_main_task_spec.json
- ChangeSpec: ./autoloop/phases_real6/phase_01/tasks/contracts/module_main_change_spec.json
- AcceptanceSpec: ./autoloop/phases_real6/phase_01/tasks/contracts/module_main_acceptance_spec.json

## Deliverables
Return strict JSON contract only.

## Human Review Patch
- Patch ID: human_review_patch_phase_01_module_main
- Reviewer: lead_integrator
- Source: ./autoloop/runtime_real6/hooks/phase_01_human_review_resolution.json
- Notes:
PATH_CONFLICT fixed by forcing artifact path under app/

You MUST apply this patch intent when producing output.

