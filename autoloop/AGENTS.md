# AGENTS.md - AutoLoop Multi-Agent Rules

This file defines rules and constraints for all AI agents working in the AutoLoop project.

## Project Overview

AutoLoop is a multi-agent orchestration system that coordinates Lead, Planner, Reviewer, Dev, and QA agents to collaboratively implement software projects. It uses:

- **LangGraph** for agent state flow and decision routing
- **Temporal** for durable execution, crash recovery, and subprocess management
- **MCP protocol** for standardized tool integration
- **Git worktrees** for agent workspace isolation
- **OpenTelemetry** for distributed tracing and observability

## Build & Run Commands

```bash
cd autoloop/

poetry install

poetry run python -m app.main init

poetry run python -m app.main run prd.md

poetry run python -m app.main run prd.md --mode temporal

poetry run pytest tests/ -v

poetry run pytest tests/ -v --cov=app --cov-report=html
```

## Testing Commands

```bash
poetry run pytest tests/ -v

poetry run pytest tests/unit/ -v

poetry run pytest tests/integration/ -v

poetry run python -m app.temporal.worker
```

## Code Style & Quality

- **Python version**: 3.11+
- **Formatter**: Black (line length 100)
- **Linter**: Ruff
- **Type checker**: MyPy (optional, not strict)
- **No comments**: Do NOT add comments unless explicitly requested
- **Use pathlib**: Always use `Path` objects for file paths, never strings
- **Structured logging**: Use structlog with JSON format
- **Async first**: All I/O operations must be async

## Commit Message Format

All agent commits MUST follow this format:

```
agent:<agent_name> phase:<phase_id> module:<module_name> summary:<what_changed>
```

Examples:

```
agent:dev phase:phase_01 module:auth summary:implement JWT authentication
agent:qa phase:phase_01 module:auth summary:add integration tests for auth
agent:planner phase:phase_02 module:api summary:design REST API architecture
```

## Agent File Access Boundaries

### Lead Agent
- **CAN READ**: All files
- **CAN WRITE**:
  - `phases/phase_*/tasks/*.md` (task assignments)
  - `phases/phase_*/phase_report.md` (final reports)
  - `runtime/hooks/*.json` (coordination signals)
- **CANNOT**: Modify application code directly

### Planner Agent
- **CAN READ**: PRD, blueprints, existing codebase
- **CAN WRITE**:
  - `phases/phase_*/tasks/planner.md` (detailed plans)
  - `phases/phase_*/results/planner.md` (planning results)
  - Module design docs (if requested)
- **CANNOT**: Modify application code

### Reviewer Agent
- **CAN READ**: All code, plans, results
- **CAN WRITE**:
  - `phases/phase_*/tasks/reviewer.md` (review comments)
  - `phases/phase_*/results/reviewer.md` (review results)
- **CANNOT**: Modify application code directly

### Dev Agent
- **CAN READ**:
  - `phases/phase_*/tasks/dev.md` (own task only)
  - Application code in assigned worktree
- **CAN WRITE**:
  - Application code files
  - `phases/phase_*/results/dev.md` (implementation results)
  - `runtime/hooks/phase_*_dev_done.json` (completion signal)
- **CANNOT**: Read or modify other agents' tasks

### QA Agent
- **CAN READ**:
  - `phases/phase_*/tasks/qa.md` (own task only)
  - Application code
  - Dev results
- **CAN WRITE**:
  - Test files
  - `phases/phase_*/results/qa.md` (test results)
  - `runtime/hooks/phase_*_qa_done.json` (completion signal)
- **CANNOT**: Modify application code (except tests)

## Security Constraints

### NEVER Do These (All Agents)

- Delete files outside your designated scope
- Execute shell commands without proper sandboxing
- Modify git configuration
- Access credentials or secrets
- Make network requests to unauthorized endpoints
- Modify files in `runtime/` except hooks
- Delete or modify other agents' worktrees

### Always Do These

- Validate file paths before reading/writing
- Use timeouts for all subprocess calls
- Log all file modifications
- Check file existence before operations
- Use proper error handling
- Report security concerns immediately

## Agent Loop Limits

To prevent infinite loops:

- **Planner ↔ Reviewer**: Maximum 3 loops per phase
- **Dev ↔ QA**: Maximum 2 loops per module
- **Review loops per module**: Maximum 2

When limit reached, Lead makes final decision.

## Git Overlap Handling

If the same file is modified by **2+ agents**:

1. System generates overlap report
2. Lead MUST review before next phase
3. Conflicts must be resolved manually
4. Regression tests must pass

**High-risk overlaps** (3+ agents): Require explicit approval

## Directory Structure

```
autoloop/
  app/              # Application code
    config.py       # Settings
    models/         # Pydantic models
    graph/          # LangGraph workflow
    temporal/       # Temporal workflows & activities
    runners/        # Agent execution adapters
    tools/          # MCP-ready tools
    gitops/         # Git worktree & overlap detection
    observability/  # Logging & tracing
    utils/          # Utilities
  runtime/
    hooks/          # Agent completion signals
    logs/           # Structured logs
    pids/           # Process tracking
  phases/
    phase_01/
      tasks/        # Agent task files
      results/      # Agent result files
      phase_report.md
  worktrees/        # Git worktrees per agent
  templates/        # Task/result templates
  tests/            # Unit & integration tests
  AGENTS.md         # This file (for Codex/Gemini)
  CLAUDE.md         # Rules for Claude Code
  README.md
  pyproject.toml
```

## File Bus Protocol

### Task File Format (`tasks/<agent>.md`)

```markdown
# <Agent> Task - Phase XX

## Context
<Background information>

## Your Tasks
1. Task 1
2. Task 2

## Constraints
- Constraint 1
- Constraint 2

## Deliverables
<What to produce>
```

### Result File Format (`results/<agent>.md`)

```markdown
# <Agent> Result - Phase XX

## Task Summary
<What was requested>

## Actions Taken
- Action 1
- Action 2

## Files Modified
- file1.py
- file2.py

## Status
SUCCESS | FAILED | BLOCKED

## Issues/Notes
<Any problems or observations>

## Next Steps
<Recommendations>
```

### Hook File Format (`hooks/phase_*_<agent>_done.json`)

```json
{
  "agent": "dev",
  "phase": "phase_01",
  "module": "auth",
  "status": "success",
  "commit_sha": "abc123...",
  "timestamp": "2024-01-15T10:30:00Z"
}
```

## Error Handling

All agents must:

1. Catch and log exceptions
2. Write error details to result.md
3. Set status to FAILED in hook
4. NOT retry without explicit instruction
5. Report blocking issues to Lead

## Integration with Codex CLI

When using Codex runner:

```bash
codex exec resume <session_id> "<prompt>" --json
```

The prompt MUST include:

- Working directory (worktree path)
- Task file path
- Result file path
- Phase ID
- Explicit instruction to NOT scan other agents' tasks

## Best Practices

1. **Idempotency**: All agent actions should be safe to retry
2. **Minimal changes**: Only modify what's necessary
3. **Clear commits**: One logical change per commit
4. **Test before commit**: Verify changes work
5. **Document blockers**: If stuck, explain why in result.md
6. **Clean up**: Remove debug/test scripts after use

## Version & Compatibility

- Python: 3.11+
- LangGraph: 0.2+
- Temporalio: 1.7+
- Git: 2.30+

## Support

For issues or questions:
- GitHub Issues: https://github.com/your-org/autoloop/issues
- Documentation: https://docs.autoloop.dev
