# AutoLoop: Multi-Agent Orchestration System

🚀 **Production-grade multi-agent collaboration engine** powered by LangGraph + Temporal + MCP

AutoLoop coordinates AI agents (Lead, Planner, Reviewer, Dev, QA) to collaboratively implement software projects through durable workflows, git worktree isolation, and structured file-based protocols.

---

## ✨ Features

- **🧠 LangGraph State Machine**: Agent workflow routing with loops, conditions, and interrupts
- **⚡ Temporal Workflows**: Durable execution, crash recovery, automatic retries
- **🔌 MCP-Ready Tools**: Standardized protocol for file, git, shell, test operations
- **🌳 Git Worktree Isolation**: Each agent works in isolated workspace, preventing conflicts
- **📊 OpenTelemetry**: Distributed tracing, structured logging, observability
- **🔒 Git Overlap Detection**: Automatic conflict detection when multiple agents modify same files
- **🎯 Loop Protection**: Configurable limits for review/revision cycles
- **📝 File Bus Protocol**: Markdown-based task/result exchange

---

## 🏗️ Architecture

```
┌─────────────┐
│   PRD.md    │
└──────┬──────┘
       │
       ▼
┌──────────────────┐
│   Lead Agent     │  Reads PRD, plans phases, generates tasks
│  (LangGraph)     │
└────────┬─────────┘
         │
         ▼
    ┌────────────────────────┐
    │  Dispatch Agents       │
    │  (Temporal Workflows)  │
    └─────┬──────────────────┘
          │
    ┌─────┴─────┬──────┬──────┐
    │           │      │      │
    ▼           ▼      ▼      ▼
┌────────┐  ┌─────┐ ┌────┐ ┌────┐
│Planner │  │ Dev │ │ QA │ │...│
└───┬────┘  └──┬──┘ └─┬──┘ └────┘
    │          │      │
    │  Git Worktrees │
    │          │      │
    └──────────┴──────┘
           │
    Write results.md
           │
           ▼
    ┌──────────────┐
    │ Lead         │  Collects results,
    │ Integrate    │  detects overlaps,
    │              │  runs integration tests
    └──────┬───────┘
           │
           ▼
    ┌──────────────┐
    │ Phase Report │
    └──────────────┘
```

---

## 🚀 Quick Start

### Prerequisites

- **Python 3.11+**
- **Git 2.30+**
- **Poetry** (recommended) or pip

### Installation

```bash
cd autoloop/

poetry install

cp .env.example .env

vi .env
```

### Initialize Project

```bash
poetry run python -m app.main init

ls -la
```

This creates:
- `prd.md` (sample PRD)
- `runtime/`, `phases/`, `worktrees/` directories
- `.env` file

### Run Your First Workflow

**Option 1: LangGraph Mode** (lightweight, good for development)

```bash
poetry run python -m app.main run prd.md --mode graph
```

**Option 2: Temporal Mock Mode** (simulates durable execution)

```bash
poetry run python -m app.main run prd.md --mode temporal
```

### Preflight & Dashboard

```bash
poetry run python -m app.main doctor prd.md --mode graph
poetry run python -m app.main run prd.md --mode graph --profile dev
poetry run python -m app.main dashboard --snapshot-only
poetry run python -m app.main system-metrics-report
poetry run python -m app.main calibrate-auto-review-policy --apply-to-default
poetry run python -m app.main governance-review --phase-id phase_01 --no-resume
```

### Check Results

```bash
ls phases/phase_01/tasks/
ls phases/phase_01/results/
cat phases/phase_01/phase_report.md

tail -f runtime/logs/*.log
```

---

## 📖 Usage

### Basic Workflow

1. **Write your PRD** (`prd.md`)
2. **Run AutoLoop**: `poetry run python -m app.main run prd.md`
3. **Check results**: `phases/phase_*/phase_report.md`

### Custom PRD Example

```markdown
# My Project PRD

## Overview
Build a REST API for user management.

## Requirements
- User CRUD operations
- JWT authentication
- PostgreSQL database

## Acceptance Criteria
- All tests pass
- API documented with OpenAPI
```

Save as `my_prd.md`, then:

```bash
poetry run python -m app.main run my_prd.md --project-id my-project
```

---

## 🧪 Testing

### Run All Tests

```bash
poetry run pytest tests/ -v
```

### Run Unit Tests Only

```bash
poetry run pytest tests/unit/ -v
```

### Run Integration Tests

```bash
poetry run pytest tests/integration/ -v
```

### Coverage Report

```bash
poetry run pytest tests/ --cov=app --cov-report=html
open htmlcov/index.html
```

---

## 🛠️ Configuration

Edit `.env` file:

```bash
AGENT_RUNNER_TYPE=codex

CODEX_SESSION_ID=your-session-id
CODEX_TIMEOUT_PROFILE=codex_balanced
CODEX_ATTEMPT_TIMEOUT_SECONDS=90
AGENT_TOTAL_TIMEOUT_SECONDS=420

TEMPORAL_MOCK_MODE=true

LLM_PROVIDER=openai
OPENAI_API_KEY=sk-...

MAX_REVIEW_LOOPS_PER_MODULE=2
GIT_OVERLAP_THRESHOLD=2

OTEL_ENABLED=true
LOG_LEVEL=INFO
```

Note: AutoLoop defaults to `codex` runner. `gemini`/`claude` are optional alternatives.
AutoLoop agent execution is driven by CLI runners and does not require local Ollama models.

### Codex Timeout Profiles

| Profile | Use Case | Attempt / Total |
| --- | --- | --- |
| `codex_fast` | smoke / pressure test | `45s / 180s` |
| `codex_balanced` | default real run | `90s / 420s` |
| `codex_debug` | deep diagnosis | `120s / 600s` |

Set `CODEX_TIMEOUT_PROFILE=custom` to keep manual timeout overrides.

## Convergence Docs

- `docs/RFC-001-convergence-control.md`
- `docs/PLAN-convergence-rollout.md`
- `docs/TODO-convergence-rollout.md`
- `docs/TEST-convergence-gates.md`
- `docs/ACCEPTANCE-convergence-gates.md`
- `docs/ARCHITECTURE-agent-control-plane.md`
- `docs/ONBOARDING-autoloop-operator.md`
- `docs/ONBOARDING-autoloop-developer.md`
- `docs/TODO-agent-execution-failure-decompose.md`
- `docs/TEST-agent-execution-failure-decompose.md`
- `docs/ACCEPTANCE-agent-execution-failure-decompose.md`

## Operations Scripts

- `python scripts/run_business_failure_monitor.py`
- `python scripts/promote_business_taxonomy.py`
- `python scripts/run_recovery_canary.py`
- `python scripts/run_business_failure_goldens.py`
- `python scripts/run_agent_execution_failure_breakdown.py --window-size 20`
- `python scripts/dump_run_dossier.py --workflow-id <id>`
- `python scripts/bootstrap_agent_project.py --target-dir <path> --project-id <id>`
- `python scripts/compare_agent_variants.py --variant-a <tagA> --variant-b <tagB>`
- `python scripts/run_codex_timeout_canary.py --prd-path ./blueprint.md --runs 5 --timeout-profile codex_balanced`

---

## 📂 Directory Structure

```
autoloop/
├── app/
│   ├── config.py              # Centralized settings
│   ├── models/                # Pydantic state models
│   │   └── state.py
│   ├── graph/                 # LangGraph workflow
│   │   ├── workflow.py
│   │   └── nodes.py
│   ├── temporal/              # Temporal workflows & activities
│   │   ├── workflow.py
│   │   ├── activities.py
│   │   ├── worker.py
│   │   └── mock_worker.py
│   ├── runners/               # Agent execution adapters
│   │   ├── base.py
│   │   ├── codex_runner.py
│   │   └── mock_runner.py
│   ├── gitops/                # Git worktree & overlap detection
│   │   ├── worktree.py
│   │   └── overlap.py
│   ├── observability/         # Logging & tracing
│   │   ├── logger.py
│   │   └── tracer.py
│   ├── utils/                 # File & process utilities
│   └── main.py                # CLI entry point
├── runtime/
│   ├── hooks/                 # Agent completion signals
│   ├── logs/                  # Structured logs
│   └── pids/                  # Process tracking
├── phases/
│   └── phase_01/
│       ├── tasks/             # Generated agent tasks
│       ├── results/           # Agent outputs
│       └── phase_report.md    # Final report
├── worktrees/                 # Git worktrees per agent
├── templates/                 # Task/result templates
├── tests/
│   ├── unit/
│   └── integration/
├── AGENTS.md                  # Rules for Codex/Gemini agents
├── CLAUDE.md                  # Rules for Claude Code
├── README.md                  # This file
├── pyproject.toml
└── .env.example
```

---

## 🔧 Advanced Usage

### Using CLI Runners (Codex, Gemini, Claude Code)

AutoLoop supports **three CLI agent runners** with session memory:

1. **Check available runners:**
```bash
poetry run python -m app.main health
```

2. **Get session ID:**
```bash
# Codex
codex session list
codex session create

# Gemini
gemini session list
gemini session create

# Claude Code
claude session list
claude session create
```

3. **Update `.env`:**
```bash
# Choose one:
AGENT_RUNNER_TYPE=codex
CODEX_SESSION_ID=abc123...

# Or:
AGENT_RUNNER_TYPE=gemini
GEMINI_SESSION_ID=xyz789...

# Or:
AGENT_RUNNER_TYPE=claude
CLAUDE_SESSION_ID=def456...
```

4. **Run workflow:**
```bash
poetry run python -m app.main run prd.md
```

**See [CLI_RUNNERS_GUIDE.md](CLI_RUNNERS_GUIDE.md) for detailed usage.**

### Using Real Temporal

1. Start Temporal server:
```bash
temporal server start-dev
```

2. Update `.env`:
```bash
TEMPORAL_MOCK_MODE=false
TEMPORAL_HOST=localhost:7233
```

3. Start worker:
```bash
poetry run python -m app.temporal.worker
```

4. Run workflow (in another terminal):
```bash
poetry run python -m app.main run prd.md --mode temporal
```

### Git Worktree Management

```python
from app.gitops import WorktreeManager

manager = WorktreeManager(Path.cwd())
worktree_path = await manager.create_worktree("dev", "phase_01")

await manager.remove_worktree("dev", "phase_01")
```

### Detecting Git Overlaps

```python
from app.gitops import detect_git_overlaps
from app.models import AgentRole

overlaps = detect_git_overlaps(
    repo_path=Path.cwd(),
    phase_id="phase_01",
    agent_commits={
        AgentRole.DEV: ["commit_sha_1", "commit_sha_2"],
        AgentRole.QA: ["commit_sha_3"],
    }
)

for overlap in overlaps:
    print(f"{overlap.file_path} modified by {overlap.agents}")
```

---

## 📝 File Bus Protocol

### Task File Format (`tasks/dev.md`)

```markdown
# Dev Task - Phase 01

## Context
Implement user authentication module.

## Your Tasks
1. Create auth/ module
2. Implement JWT middleware
3. Write unit tests

## Constraints
- Use async/await
- Follow Black formatting

## Deliverables
Write result.md with implementation summary.
```

### Result File Format (`results/dev.md`)

```markdown
# Dev Result - Phase 01

## Task Summary
Implemented JWT authentication.

## Actions Taken
- Created app/auth/jwt.py
- Added middleware
- Wrote 10 unit tests

## Files Modified
- app/auth/jwt.py (new)
- app/middleware.py (modified)

## Status
SUCCESS

## Commit Information
- SHA: abc123
- Message: agent:dev phase:phase_01 module:auth summary:implement JWT

## Next Steps
QA should verify token expiration logic.
```

---

## 🎯 Agent Roles

| Agent | Responsibility | Inputs | Outputs |
|-------|---------------|--------|---------|
| **Lead** | Planning, integration, reporting | PRD | tasks/*.md, phase_report.md |
| **Planner** | Detailed design, module breakdown | PRD, requirements | planner.md (design) |
| **Reviewer** | Code review, architecture feedback | Code, plans | reviewer.md (feedback) |
| **Dev** | Implementation | tasks/dev.md | Code changes, results/dev.md |
| **QA** | Testing, validation | tasks/qa.md, code | Test results, results/qa.md |

---

## 🔒 Security & Constraints

### Agent File Access Boundaries

- **Lead**: Can read all files, write to `phases/*/tasks/`, `phases/*/phase_report.md`
- **Dev**: Can read own task, write to application code and `results/dev.md`
- **QA**: Can read own task and code, write to tests and `results/qa.md`

### Loop Protection

- **Planner ↔ Reviewer**: Max 3 loops
- **Dev ↔ QA**: Max 2 loops per module

### Git Overlap Handling

- **2+ agents** modifying same file → Generates overlap report
- **High-risk** (3+ agents) → Requires manual approval before next phase

---

## 📊 Observability

### Structured Logging

```bash
tail -f runtime/logs/run_agent_20240115.log
```

Logs are JSON formatted with trace IDs.

### OpenTelemetry Traces

When `OTEL_ENABLED=true`:

```bash
grep "trace_id" runtime/logs/*.log
```

Future: Export to Jaeger/OTLP for visualization.

---

## 🐛 Troubleshooting

### Tests Failing

```bash
poetry run pytest tests/ -v --tb=short
```

### Agent Not Executing

Check logs:
```bash
cat runtime/logs/phase_01_dev.log
```

Verify runner type in `.env`:
```bash
AGENT_RUNNER_TYPE=mock
```

### Temporal Connection Error

If using real Temporal:
```bash
temporal server start-dev
```

Or use mock mode:
```bash
TEMPORAL_MOCK_MODE=true
```

### Git Worktree Issues

Clean up:
```bash
git worktree prune
rm -rf worktrees/
```

---

## 🗺️ Roadmap

### MVP (Current)
- ✅ Lead → Dev → QA flow
- ✅ Mock agent execution
- ✅ Task generation & result collection
- ✅ Phase reports
- ✅ Git overlap detection

### Phase 2
- ⬜ Planner ↔ Reviewer loop
- ⬜ Real Codex runner integration
- ⬜ Multi-module parallelization
- ⬜ Advanced git merge strategies

### Phase 3
- ⬜ Real-time Temporal worker
- ⬜ Web dashboard for monitoring
- ⬜ LLM-powered code review
- ⬜ Automatic conflict resolution

---

## 📚 References

- **LangGraph**: https://langchain-ai.github.io/langgraph/
- **Temporal**: https://docs.temporal.io/
- **MCP**: https://spec.modelcontextprotocol.io/
- **OpenTelemetry**: https://opentelemetry.io/

---

## 🤝 Contributing

See `AGENTS.md` and `CLAUDE.md` for development guidelines.

### Code Style

- Python 3.11+
- Black formatter (line length 100)
- Ruff linter
- No comments unless requested
- Async-first for I/O

### Commit Message Format

```
agent:<name> phase:<phase_id> module:<module> summary:<changes>
```

Example:
```
agent:dev phase:phase_01 module:auth summary:implement JWT middleware
```

---

## 📄 License

MIT License - See LICENSE file for details

---

## 📧 Support

- GitHub Issues: https://github.com/your-org/autoloop/issues
- Documentation: https://docs.autoloop.dev (coming soon)

---

**Built with ❤️ for AI-powered collaborative software development**
