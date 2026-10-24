# Changelog

All notable changes to the AutoLoop project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2024-01-15

### 🎉 Initial MVP Release

#### Added

##### Core Architecture
- **LangGraph State Machine**: Complete workflow with 8 nodes (lead_plan, dispatch_dev, wait_dev, dispatch_qa, wait_qa, lead_integrate, phase_done, phase_fail)
- **Temporal Workflows**: Durable execution with 7 activities and retry policies
- **MCP-Ready Tool Layer**: Standardized protocol for future integration
- **Pydantic Models**: Type-safe data structures (ProjectState, PhaseState, AgentRole, AgentStatus, etc.)

##### Agent Execution
- **BaseAgentRunner**: Abstract interface for all agent runners
- **CodexRunner**: Real Codex CLI integration with session management
- **MockRunner**: Fully functional mock agent for testing
- **AgentRunContext**: Structured context passing to agents
- **AgentRunResult**: Standardized result format

##### Git Operations
- **WorktreeManager**: Create/remove isolated git worktrees per agent
- **Overlap Detection**: Automatic conflict detection when multiple agents modify same files
- **Risk Assessment**: High/medium risk levels for git overlaps
- **Commit Tracking**: Track agent commits per phase

##### Observability
- **Structured Logging**: JSON formatted logs with structlog
- **OpenTelemetry Tracing**: Distributed tracing with console/OTLP exporters
- **Event Logging**: Key events logged to files
- **Trace Decorators**: `@trace_workflow` and `@trace_activity`

##### File Bus Protocol
- **Task Files**: Markdown-based task assignments (`phases/*/tasks/*.md`)
- **Result Files**: Markdown-based agent outputs (`phases/*/results/*.md`)
- **Hook Files**: JSON completion signals (`runtime/hooks/*.json`)
- **Phase Reports**: Comprehensive phase summaries

##### CLI Interface
- **Typer CLI**: User-friendly command-line interface
- **Init Command**: Initialize new projects
- **Run Command**: Execute workflows with mode selection
- **Rich Output**: Colored terminal output with Rich library

##### Configuration
- **Pydantic Settings**: Type-safe configuration management
- **Environment Variables**: 20+ configurable settings via .env
- **Multiple Modes**: LangGraph, Temporal mock, Temporal real
- **Runner Selection**: Mock or Codex runner via config

##### Testing
- **Unit Tests**: 15+ tests covering models, utils, runners
- **Integration Tests**: 3+ end-to-end workflow tests
- **Pytest Fixtures**: Reusable test fixtures (temp dirs, mock settings)
- **Coverage Support**: HTML coverage reports

##### Documentation
- **README.md**: Comprehensive user guide (3000+ words)
- **AGENTS.md**: Rules for Codex/Gemini agents (2000+ words)
- **CLAUDE.md**: Rules for Claude Code (2500+ words)
- **PROJECT_STRUCTURE.md**: Complete architecture guide (2000+ words)
- **GETTING_STARTED.md**: Step-by-step quick start guide
- **SUMMARY.md**: Implementation overview
- **CHANGELOG.md**: This file

##### Templates
- **task_template.md**: Standard task file format
- **result_template.md**: Standard result file format
- **phase_report.md**: Phase report template
- **prd_example.md**: Complete example PRD (Calculator API)

##### Utilities
- **File Utils**: Task/result file path generation and I/O
- **Process Utils**: Subprocess execution with timeout and cleanup
- **Directory Management**: Auto-create runtime, phases, worktrees dirs
- **Path Handling**: Pathlib-based path management

##### Scripts
- **quickstart.sh**: Automated setup and initialization
- **pyproject.toml**: Poetry dependencies and project metadata
- **.env.example**: Environment variable template

#### Features

##### MVP Workflow
- ✅ PRD input → Lead plans → Generate tasks → Dispatch Dev → Dispatch QA → Integrate → Report
- ✅ Task generation from PRD
- ✅ Agent execution (mock mode)
- ✅ Result collection
- ✅ Git overlap detection
- ✅ Phase reporting

##### Execution Modes
- **LangGraph Mode**: Lightweight state machine execution
- **Temporal Mock Mode**: Simulates durable execution without server
- **Temporal Real Mode**: Production-ready durable workflows (requires server)

##### Agent Isolation
- Git worktree support (ready, not enforced in mock mode)
- File access boundaries defined
- Commit message format enforcement

##### Loop Protection
- Max Planner ↔ Reviewer loops: 3
- Max Dev ↔ QA loops: 2
- Configurable loop limits

##### Observability
- JSON structured logs
- OpenTelemetry traces
- Event-based logging
- File and console output

#### Technical Details

##### Dependencies
- Python 3.11+
- LangGraph 0.2+
- Temporalio 1.7+
- Pydantic 2.9+
- GitPython 3.1+
- OpenTelemetry 1.27+
- Structlog 24.4+
- Typer 0.12+
- Rich 13.7+
- Pytest 8.3+

##### Code Quality
- Black formatted (line length 100)
- Ruff linting compatible
- Type hints with Pydantic
- Async-first architecture
- ~3000+ lines of code
- ~60 files

##### Test Coverage
- Unit tests for core utilities
- Integration tests for workflows
- Mock fixtures for isolation
- Pytest-asyncio support

### 🔜 Planned for v0.2.0

#### Features
- [x] Planner ↔ Reviewer loop implementation
- [x] Multi-module parallelization
- [x] Real Codex runner integration (tested)
- [x] Advanced git merge strategies
- [x] Automatic conflict resolution

#### Improvements
- [x] Web dashboard for monitoring
- [x] Real-time progress updates
- [x] LLM-powered code review
- [x] Enhanced error recovery

### 🚧 Stubbed/Not Yet Implemented

- Integrator agent specialization (shared with lead control loop)
- Real Temporal worker deployment/operations wiring
- MCP server runtime adapter (protocol layer ready)
- Lead-agent model policy tuning (config exists, policy tuning pending)

### 📝 Notes

#### Design Decisions
- **Mock-first approach**: Allows rapid testing without external dependencies
- **File bus protocol**: Decouples agents, easy to debug
- **Git worktree isolation**: Prevents conflicts, enables parallelization
- **Dual execution modes**: Flexibility for dev vs production
- **OpenTelemetry ready**: Production observability from day one

#### Known Limitations
- Production Temporal deployment still requires infrastructure setup
- Single-phase execution default (multi-phase orchestration is incremental)
- Dashboard currently serves snapshot/status endpoints
- Conflict auto-resolution uses deterministic strategy (`ours` by default)

### 🙏 Acknowledgments

Built with:
- [LangGraph](https://langchain-ai.github.io/langgraph/) for state machine workflows
- [Temporal](https://temporal.io/) for durable execution
- [Pydantic](https://pydantic.dev/) for data validation
- [OpenTelemetry](https://opentelemetry.io/) for observability

---

## Version History

| Version | Date | Status | Notes |
|---------|------|--------|-------|
| 0.1.0 | 2024-01-15 | ✅ Released | MVP with LangGraph + Temporal + Mock agents |
| 0.2.0 | TBD | 🚧 Planned | Planner/Reviewer loop, multi-module |
| 0.3.0 | TBD | 🚧 Planned | Web dashboard, LLM integration |

---

## Migration Guide

### From simpleautoloop to autoloop

If you're migrating from the old `simpleautoloop` directory:

1. **Install new version:**
   ```bash
   cd autoloop/
   poetry install
   ```

2. **Copy your PRD:**
   ```bash
   cp ../simpleautoloop/project/prd.md ./prd.md
   ```

3. **Run with new system:**
   ```bash
   poetry run python -m app.main run prd.md
   ```

4. **Key differences:**
   - New: LangGraph state machine (vs custom orchestrator)
   - New: Temporal workflows (vs direct execution)
   - New: Structured observability (vs simple logging)
   - New: Git worktree support (vs single workspace)
   - New: Type-safe models (vs dictionaries)

---

**For detailed usage instructions, see [GETTING_STARTED.md](GETTING_STARTED.md)**

**For architecture details, see [PROJECT_STRUCTURE.md](PROJECT_STRUCTURE.md)**

**For development guidelines, see [CLAUDE.md](CLAUDE.md) and [AGENTS.md](AGENTS.md)**
