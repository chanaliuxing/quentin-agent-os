# RFC: Shutdown Terminal Fallback

## Objective
- Guarantee terminal event closure on `SIGINT`/`SIGTERM`/forced shutdown.
- Ensure terminal runs always include `WORKFLOW_TERMINATED`.

## Design
- Introduce centralized `ShutdownManager` in app entry to capture `SIGINT` and `SIGTERM`.
- Use single write primitive `write_terminal_event_once(...)` for all terminal paths.
- On shutdown interrupt:
  - stop scheduling new work,
  - write minimal terminal closure (`WORKFLOW_TERMINATED`, terminal metadata, summary),
  - preserve existing business primary cause when present.

## Invariants
- `primary_failure_type` is never `NONE/UNKNOWN/NULL`.
- shutdown labels append terminal semantics; they do not overwrite existing business primary cause.
- terminal write is idempotent per `project_id + phase_id`.

## Validation
- Unit tests for SIGINT and SIGTERM write paths.
- Unit test for timeout/abort preserving existing primary cause.
- SLO report must fail with `MISSING_TERMINAL_EVENT` when terminal event is absent.
