# TODO: Observability Sinks + Event Store Backends

Date: 2026-02-11
Scope: `quentin/observability/*`, `quentin/runtime/system_events.py`, `meta_agent/api/*`, `tests/*`

Problem:
- Observability and system events exist but storage/backends are implicit.
- Adding new sinks (file, sqlite, remote) requires wiring changes.
- Runtime sensing should be text-only but structured and queryable.

Goal:
- Introduce:
  - `EventStoreBackend` for `system_events`
  - `ObservabilitySink` interface for new sinks
- Default backends remain file-based (current behavior).

Non-goals:
- Do not introduce network dependencies by default.

Design (proposal):
- `EventStoreBackend`:
  - `append(event)`, `drain(session_id, limit)`, `list_sessions()`
- `ObservabilitySink`:
  - `record(trace_event)` / `record_metric(name, value, tags)`
- Config:
  - `QUENTIN_OBS_EVENT_STORE_BACKEND=file` (default)

Implementation Steps:
- [x] Add `quentin/runtime/event_store/` with `base.py`, `file_backend.py`.
- [x] Update `quentin/runtime/system_events.py` to use backend abstraction.
- [x] Update `meta_agent/api/server.py` endpoints to query through backend.
- [x] Tests:
  - [x] `tests/unit/test_event_store_backend_file.py`.
  - [x] `tests/integration/test_system_events_api_backend.py`.

Acceptance Criteria:
- Switching backend does not change event schema.
- Brain can query recent error events reliably (sensing).

Rollback:
- `QUENTIN_OBS_EVENT_STORE_BACKEND=file`.
