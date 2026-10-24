# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Project Quentin is a **self-evolving meta-agent operating system** (Meta-Agent v3 Research Edition). It's a research-friendly framework for building autonomous agents that can:
- Execute tasks through a cognitive loop
- Maintain multi-tier memory (STS/MTS/LTS)
- Self-diagnose and recover via an immune system
- Self-program and evolve capabilities within safety boundaries

**Key Principle:** This is a research scaffold, not production software. Most modules are placeholder implementations awaiting real algorithms.

## Architecture: Four-Layer Design

```
L3 Research & Evolution    # Experiment orchestration, evolution strategies
L2 Meta Layer             # Self-improvement, evaluation, immune response
L1 Base Layer             # Cognitive loop, memory, planning, execution
L0 Infra & Kernel         # Safety kernel, storage, logging (not AI-modifiable)
```

### Dual Package Structure

- **`quentin/`**: Original v3 architecture implementation with modules for cognitive loops, memory fabric, routing, experiments, and self-programming
- **`meta_agent/`**: Parallel implementation focusing on blueprint-driven development, self-programming engine v2, immune system, and multi-LLM council

Both packages coexist and share some concepts but have different architectural approaches.

## Common Commands

### Installation
```bash
# Install in development mode
pip install -e .

# Core dependencies: pydantic, fastapi, uvicorn, click, chromadb, httpx, pyyaml
```

### Running Tests
```bash
# Run all tests
pytest

# Run specific test file
pytest tests/test_file_patcher.py

# Run with verbose output
pytest -v
```

### Task Execution (qctl CLI)
```bash
# Run a task through the cognitive loop
qctl run-task --input-text "Your task description" --domain core --environment sandbox

# View observability metrics
qctl metrics-overview

# Start observability API server (exposes /health, /overview, /models, etc.)
qctl serve-observability --host 0.0.0.0 --port 8000
```

### Skill Management
```bash
# List all registered skills
qctl skills-list

# Filter skills by status (candidate/active/deprecated)
qctl skills-list --status candidate

# Suggest skills for a task
qctl skills-suggest "analyze log files" --domain core --top-k 5

# Implement a candidate skill
qctl skill-impl <skill_id>

# Automatically pick and implement next candidate skill
qctl skill-impl-next --domain core
```

### Self-Programming & Patches
```bash
# Propose and apply a patch (new workflow)
qctl selfprog-patch --target quentin/core/cognitive_loop.py --reason "Fix bug in task execution" --risk-level high

# List existing patches
qctl patch-list --status proposed

# Show patch details
qctl patch-show --patch-id <patch_id>
```

### Blueprint Management
```bash
# Scan codebase against blueprint spec
qctl blueprint-scan --blueprint-path blueprint/spec_v3.json

# View detailed status of a blueprint item
qctl blueprint-item <item_id>

# Auto-generate patches for missing/partial capabilities
qctl blueprint-autopatch --status missing,partial --eval
```

### Immune Loop
```bash
# Process a single trace file
qctl immune-process-trace --trace-file path/to/trace.json

# Run immune loop to detect anomalies
qctl immune-run --window-minutes 60 --enable-self-fix
```

### Sleep Loop (Memory Consolidation)
```bash
# Run sleep loop for memory consolidation and skill mining
qctl sleep-run --hours 24
```

### Experiments & Research
```bash
# List experiments
qctl exp-list

# View runs for an experiment
qctl exp-runs --experiment-id <exp_id>

# Compare variants on a metric
qctl exp-compare --experiment-id <exp_id> --metric success_rate --top-k 5

# Export experiment results
qctl exp-export --experiment-id <exp_id> --output results.json
```

### Model Router
```bash
# Show current router rules
qctl router-show

# Optimize router based on collected stats
qctl router-optimize --weight-latency 0.1
```

### Policy & Budget
```bash
# Show policy constitution and recent decisions
qctl policy-show --decisions-tail 10

# Show budget profiles and usage
qctl budget-show
```

## Key Architectural Concepts

### Four Loops System

1. **Cognitive Loop** (`quentin/core/cognitive_loop.py`):
   - Task → Plan → Execute → Critique → Memory
   - All steps must generate ExecutionTrace records
   - Entry point for task execution

2. **Immune Loop** (`quentin/loops/immune_loop.py`):
   - Monitors error rates, latency, cost metrics
   - Creates ImmuneCases for anomalies
   - Can trigger automatic rollback or self-fix patches

3. **Sleep Loop** (`quentin/loops/sleep_loop.py`):
   - Periodic consolidation (nightly/weekly)
   - Migrates memory between tiers (STS → MTS → LTS)
   - Mines skills from successful execution traces
   - Scans blueprint gaps and proposes patches

4. **Evolution Loop** (distributed across self-programming and research modules):
   - Generates code patches from immune cases or blueprint gaps
   - Runs experiments to compare variants
   - Manages skill lifecycle: candidate → active → deprecated

### Memory Fabric

Three-tier memory system in `quentin/memory/fabric.py`:
- **STS (Short-Term Store)**: Session/task-level context
- **MTS (Mid-Term Store)**: Project/version-level patterns
- **LTS (Long-Term Store)**: Cross-project stable knowledge

Memory promotion happens during sleep consolidation based on access patterns and usefulness.

### Self-Programming Engine

Located in both:
- `quentin/self_programming/engine.py` (original)
- `meta_agent/self_programming/engine.py` (v2 with multi-agent architecture)

Key safety constraints:
- **SafetyKernel** controls what can be modified (only files in `/mutable/` or marked `auto_updatable`)
- **PolicyEngine** enforces environment rules (no auto-apply in production)
- **BudgetController** limits token/cost usage
- All patches require human gate approval for high-risk domains

### LLM Integration

The system is **LLM-agnostic**. To integrate your own LLM:

1. Implement in `quentin/llm/client.py` or use existing clients:
   - `meta_agent/llm/ollama_client.py` for Ollama
   - `meta_agent/llm/cli_client.py` for CLI-based LLMs
   - `quentin/infra/llm/dummy_client.py` for testing

2. Register models in `ModelRouter` (`quentin/models/router.py`)

3. Update placeholder calls in:
   - `quentin/agents/roles.py` (BaseRoleAgent.run)
   - `quentin/cognitive/loop.py` (Planner/Critic)
   - `quentin/self_programming/engine.py` (patch generation)

## Code Organization Patterns

### Module Naming Conventions

- `schemas.py` / `types.py`: Pydantic models and type definitions
- `store.py` / `registry.py`: Data persistence layer
- `manager.py`: High-level orchestration
- `engine.py`: Core execution logic
- `loop.py`: Periodic/cyclical processes
- `*_tool.py`: Tool implementations for agents

### Blueprint-Driven Development

The project uses `blueprint/spec_v3.json` to track implementation status of architectural components. Each blueprint item has:
- `id`: Unique identifier
- `layer`: L0/L1/L2/L3
- `phase`: foundation/consolidation/optimization/research
- `required_capabilities`: Expected functionality
- `hints`: Implementation guidance

Use `qctl blueprint-scan` to see what needs implementation.

### Testing Strategy

Tests are in `tests/` directory:
- `tests/test_*.py`: Unit tests for specific modules
- `tests/integration/`: Integration tests for multi-component flows

The test suite is **incomplete** - most modules have placeholder or partial tests. When adding features, prioritize:
1. Testing safety-critical paths (SafetyKernel, PolicyEngine)
2. Testing data integrity (Memory, Traces, Patches)
3. Integration tests for complete loops

## Development Workflow

### Adding a New Capability

1. Check if it exists in `blueprint/spec_v3.json`
2. If yes: use `qctl blueprint-item <item_id>` to understand requirements
3. Implement in appropriate layer (L0/L1/L2/L3)
4. Add execution traces for observability
5. Write tests (at minimum: happy path + error handling)
6. Update blueprint status if applicable

### Replacing Placeholder Implementations

Many modules have "echo" or "stub" implementations marked with comments like:
```python
# TODO: Replace with real LLM call
# TODO: Replace with vector search
# TODO: Implement actual algorithm
```

When replacing:
1. Preserve the function signature and return type
2. Maintain ExecutionTrace logging
3. Add error handling and metrics
4. Consider adding experiment variants for A/B testing

### Working with Self-Programming

The self-programming engine can modify code in `quentin/mutable/` directory. When working on self-modifiable components:

1. **Never** place safety-critical code in `/mutable/`
2. All self-programming must go through PolicyEngine checks
3. Test patches in `sandbox` environment first
4. Use `environment=staging` for limited rollout
5. High-risk changes require human gate approval (set in PolicyEngine constitution)

## Important Constraints

### What AI Cannot Modify

- **L0 (Kernel/Infra)**: Safety kernel, base schemas, logging infrastructure
- **Constitution files**: Policy engine rules, budget profiles
- **High-risk domains**: Legal, Trading core logic (can only modify adapters/tools)

### Safety Boundaries

- All self-programming operations are logged in ExecutionTrace
- Patches can be rolled back using backup files
- Immune loop can trigger automatic rollback on anomaly detection
- Budget controller enforces token/cost limits per domain

## Configuration Files

- `pyproject.toml`: Package metadata and dependencies
- `blueprint/spec_v3.json`: Architectural blueprint and implementation tracking
- `config/model_router_rules.json`: Model routing policies (auto-generated by optimizer)
- `config/policy_constitution.yaml`: Policy engine rules (if exists)
- `data/*.jsonl`: Runtime data (skills, patches, traces, experiments)

## Observability & Debugging

### Viewing System State

```bash
# Quick overview of all metrics
qctl metrics-overview

# Start API server and view in browser
qctl serve-observability --port 8000
# Visit http://localhost:8000/overview
```

### Trace Analysis

Execution traces are stored in `data/traces/` or via ExecutionTraceStore. Each trace contains:
- Task/goal context
- Success/failure status
- Error type and message
- Performance metrics
- Blueprint capability mapping

Use traces to:
- Debug task failures
- Mine new skills (via sleep loop)
- Identify immune system triggers
- Track blueprint implementation progress

### Metrics to Monitor

- **Model usage**: Success rate, latency, cost per model
- **Memory**: Distribution across STS/MTS/LTS tiers
- **Immune cases**: Frequency and severity of anomalies
- **Patches**: Success rate of self-programming attempts
- **Skills**: Growth of skill library, usage patterns

## Research Extensions

This framework is designed for research experimentation:

### Pluggable Algorithms

Replace these with your own implementations:
- Memory consolidation strategy (`MemoryFabric.consolidate_once`)
- Skill mining algorithm (`SkillMiner.mine_from_episodes`)
- Model routing policy (`MultiAgentCoordinator.choose_model`)
- Patch generation (`SelfProgrammingEngine.generate_patch`)

### Experiment Framework

Use `ExperimentOrchestrator` for A/B testing:
```python
from quentin.experiments.orchestrator import ExperimentOrchestrator
from quentin.experiments.schemas import ExperimentConfig, ExperimentVariant

# Define variants
variants = [
    ExperimentVariant(variant_id="baseline", name="baseline", params={"strategy": "old"}),
    ExperimentVariant(variant_id="new", name="new_algo", params={"strategy": "new"}),
]

# Run experiment
orchestrator = ExperimentOrchestrator()
exp = await orchestrator.create_experiment(
    name="planner_comparison",
    config=ExperimentConfig(target_module="planner", metrics=["success_rate", "latency"]),
    variants=variants,
)

await orchestrator.run_experiment(exp.experiment_id)
results = await orchestrator.compare_variants(exp.experiment_id, metric="success_rate")
```

## Common Pitfalls

1. **Missing ExecutionTrace**: Many commands fail if traces aren't properly logged. Always create traces for operations.

2. **Schema Mismatches**: The project has undergone refactoring. Some old commands use deprecated schemas (marked as `_deprecated` in qctl.py).

3. **LLM Not Configured**: Many operations assume LLM client is configured. Set `LLM_MODEL` environment variable or implement `call_llm` in `quentin/llm/client.py`.

4. **Blueprint Out of Sync**: After adding features, run `qctl blueprint-scan` to update implementation status.

5. **Circular Dependencies**: The `quentin` and `meta_agent` packages have some circular dependencies. Be careful when importing across package boundaries.
