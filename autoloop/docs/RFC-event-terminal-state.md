# RFC: Event Schema + Terminal State Machine (Implementation v1)

## Goal
- Promote provenance from result-level inference to event-level facts.
- Make `terminal_state` a first-class workflow output, not a post-hoc guess.

## Event Schema (failure_events[])
Each event item persisted in evidence includes:

| Field | Type | Meaning |
|---|---|---|
| `event_time` | string | Observation time (workflow/activity boundary time). |
| `stage` | string | Stage name (`planner`/`reviewer`/`dev`/`qa`/acceptance variants). |
| `actor` | string | Producing actor/agent. |
| `attempt` | int | Attempt index (v1 defaults to `1`). |
| `cause_type` | string | Structured failure type code. |
| `cause_class` | string | `business` / `contract` / `execution` / `infra` / `unknown`. |
| `is_primary_candidate` | bool | Whether event participates in primary-cause ranking. |

## Terminal State Machine (workflow output)

| Condition | terminal_state |
|---|---|
| `acceptance_status=passed` | `ACCEPTED` |
| any timeout signal (`GLOBAL_TIMEOUT`) | `TIMEOUT` |
| `recommended_action=escalate_to_human` | `ABORTED` |
| otherwise (rejected flow) | `REJECTED` |

## Primary/Secondary Cause Rules
- Primary: selected by priority ranking then observation order.
- Secondary: all other structured failures kept as append-only context.
- Final label (`final_status_label`) remains separate from `primary_failure_type`.

## Acceptance
- Evidence file must contain: `terminal_state`, `primary_failure_type`, `secondary_failure_types`, `failure_events`.
- Real run must produce deterministic `terminal_state` and non-empty `failure_events` on failed cases.
