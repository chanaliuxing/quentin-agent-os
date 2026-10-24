# CLAUDE.md

This repository supports multiple coding agents.

## Scope
- Implement tasks assigned in `phases/<phase_id>/tasks/`.
- Write outputs to `phases/<phase_id>/results/`.
- Keep edits minimal and focused on assigned modules.

## Guardrails
- Use Python 3.11+.
- Prefer async I/O paths in application code.
- Use `Path` from `pathlib` for filesystem access.
- Run targeted tests before finishing changes.

## Commands
```bash
poetry run pytest tests/unit/ -v
poetry run pytest tests/integration/ -v
poetry run python -m app.main run prd.md
```
