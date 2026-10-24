# Repository Guidelines

## Project Structure & Module Organization
- Core packages live in `quentin/` (cognitive loop, planning, tools, self_programming) and `meta_agent/` (API surface and supporting services). Each subpackage mirrors a functional area (`memory`, `skills`, `kernel`, `loops`, `research`, etc.).
- Scripts for running cycles, demos, and maintenance tasks sit in `scripts/` (for example `run_api_server.py`, `run_self_programming_cycle_v2.py`, `run_blueprint_cycle.py`).
- Tests are under `tests/` with `unit/`, `integration/`, and focused smoke checks like `test_toy_planner.py`.
- Data and runtime artifacts default to `data/`, `logs/`, and `chroma_db_code_chunks/`; keep these out of commits unless explicitly required.

## Build, Test, and Development Commands
- Create an environment with Python 3.10+: `python -m venv .venv && source .venv/bin/activate`.
- Install locally: `python -m pip install -e .` (pulls dependencies from `pyproject.toml`).
- Run unit tests quickly: `pytest tests/unit -q`; full suite: `pytest`.
- Exercise the CLI: `python -m quentin.cli.qctl --help` or `python -m quentin.cli.qctl run-task --input-text "hello"`.
- Start the observability/API server during development: `python scripts/run_api_server.py` (serves `meta_agent.api.server:app` on port 8000).

## Coding Style & Naming Conventions
- Python-first codebase; use 4-space indentation, type hints, and prefer dataclasses or Pydantic models for configs and schemas.
- Modules and functions use `snake_case`; classes use `CamelCase`; CLI commands are hyphenated via Click options.
- Keep components small and composable (follow existing `*Loop`, `*Manager`, `*Engine` patterns). Add concise docstrings when behavior is non-obvious.
- When adding config, prefer explicit `Settings`/`Config` objects under `quentin.config` or `meta_agent.config` instead of ad-hoc globals.

## Testing Guidelines
- Default test runner is `pytest`; place new unit tests in `tests/unit` and integration flows in `tests/integration`.
- Name tests `test_<module>.py` and functions `test_<behavior>`; prefer fixtures in `tests/conftest.py` over inline setup.
- For new features, add a targeted test and run the relevant subset (`pytest tests/test_toy_planner.py -q`) before sending a PR.

## Commit & Pull Request Guidelines
- Use short, imperative commit messages; prefix with the touched area when helpful (e.g., `planning: tighten goal checks`). Both English and concise Chinese are acceptable; keep the summary under ~72 chars.
- Before opening a PR, note what changed, why, and how you tested (commands and scope). Link related issues or design docs and include screenshots for UI/observability changes if applicable.
- Avoid committing generated artifacts, local databases, or virtualenvs; ensure `data/`, `logs/`, and cache dirs stay untracked unless explicitly reviewed.

## Security & Configuration Notes
- Do not hardcode secrets or tokens; load them via environment variables consumed by settings objects (`quentin.config.settings`, `meta_agent.config`).
- If you introduce new external endpoints or model providers, document required env vars and safe defaults. Keep sandbox/staging defaults conservative to protect production-like runs.
