# Session Auto Management

Runner sessions are tracked to improve continuity and reduce setup friction.

## Storage
- Session metadata is persisted by `app.runners.session_manager.SessionManager`.
- Session files are organized per runner type.

## Behavior
- Runners can reuse existing session IDs when available.
- Cleanup keeps recent sessions and removes stale entries when requested.

## Operations
```bash
poetry run python -m app.main sessions --runner-type codex
poetry run python -m app.main sessions --runner-type codex --cleanup
```
