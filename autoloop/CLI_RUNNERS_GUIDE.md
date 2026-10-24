# CLI Runners Guide

This guide describes runner behavior used by `app.main`.

## Available Runners
- `mock`: Local simulation for development and dry-runs.
- `codex`: Codex CLI-backed execution.
- `gemini`: Gemini CLI-backed execution.
- `claude`: Claude CLI-backed execution.

## Codex Resume Policy
- `codex` defaults to `resume -> standard -> ephemeral` when `CODEX_SESSION_ID` is configured and the session rollout file passes a resume smoke check.
- If the rollout file is missing, the resume probe fails, or `state_db` degradation is detected, the runner skips or abandons `resume` and falls back automatically.
- Placeholder values such as `your-codex-session-id` are treated as unset and will not trigger resume mode.

## AgentSpec + SessionResolver
- Session resolution is policy-driven by role/project/worktree scope.
- Default scope mapping:
  - `planner`, `reviewer` -> `by_role_project`
  - `dev`, `qa` -> `by_role_worktree`
- Resolution priority:
  1. `AGENT_SPECS_JSON` role-level `session_id`
  2. context env override (`CODEX_SESSION_ID` in runner env vars)
  3. global `CODEX_SESSION_ID` fallback
  4. empty session (`standard/ephemeral` only)
- Configure role policies with `AGENT_SPECS_JSON`:

```bash
export AGENT_SPECS_JSON='{
  "planner":{"session_scope":"by_role_project"},
  "reviewer":{"session_scope":"by_role_project"},
  "dev":{"session_scope":"by_role_worktree","session_id":"dev-session-id"},
  "qa":{"session_scope":"by_role_worktree","session_id":"qa-session-id"}
}'
```

## Key CLI Commands
```bash
poetry run python -m app.main run prd.md --mode graph
poetry run python -m app.main run prd.md --mode temporal
poetry run python -m app.main doctor prd.md --mode graph
poetry run python -m app.main sessions --runner-type codex
```

## Profiles
- `dev`: permissive local mode.
- `prod`: stricter checks (no mock runner; temporal mock disabled in temporal mode).
