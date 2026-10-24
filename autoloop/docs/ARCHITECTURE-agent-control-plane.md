# Architecture: Agent Control Plane

## Lanes

### 1) Control Plane Lane (Frozen)
- Core contracts: event log, execution summary, terminal state, SLO gate.
- Key artifacts:
  - `runtime/event_log/<workflow>/<phase>/events.jsonl`
  - `runtime/evidence/<workflow>/<phase>/execution_summary.json`
  - `runtime/metrics/control_plane_slo_report.json`
- Gate boundary: `scripts/ci_control_plane_gate.sh` only validates control-plane invariants.

### 2) Business Convergence Lane
- Inputs: `primary_failure_type`, `failure_events`, `terminal_state`.
- Components:
  - `app/metrics/business_failure_signature_normalizer.py`
  - `scripts/promote_business_taxonomy.py`
  - `scripts/run_business_failure_monitor.py`
  - replay goldens under `tests/replay/business_failure_golden_pack/`
- Outputs:
  - `runtime/metrics/business_failure_monitor_report.json`
  - `runtime/metrics/business_failure_promotion_report.json`
  - `runtime/hooks/taxonomy_ticket_*.json`

### 3) Recovery Rollout Lane
- Components:
  - `app/control/recovery_rollout_policy.py`
  - `policies/recovery_rollout_policy.json`
  - `scripts/run_recovery_canary.py`
- Modes: `shadow -> canary -> full`.
- Output: `runtime/metrics/recovery_canary_report.json`.

## Interface Contract
- Control plane publishes facts.
- Business lane consumes facts and proposes taxonomy/playbook upgrades.
- Recovery lane consumes facts + policy and controls execution safety.
- No lane modifies control-plane schema without explicit RFC.

## Harness View
- `AgentHarness` abstraction encapsulates:
  - collect run artifacts,
  - evaluate metrics snapshots,
  - produce dossier markdown.
- Current implementation: `app/harness/core.py`.
